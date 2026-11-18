"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    rows, base_rows = pr.get("rows") or [], base.get("rows") or []
    graded = [m["id"] for m in spec["metrics"] if base_rows and m["id"] in base_rows[0]]
    # 1. metric values must be real numbers
    for mid, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {mid} is {v}")
    # 2. graders must not have crashed, and no graded cell may be missing
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s) in the PR run")
    missing = [f"{r.get('item_id')}@{r.get('seed')}:{m}" for r in rows for m in graded if not isinstance(r.get(m), bool)]
    if missing:
        problems.append(f"{len(missing)} graded value(s) missing or not a bool (None/NaN), first {missing[0]}")
    # 3. row count and the exact (item, seed) grid: nothing dropped, duplicated or cherry-picked
    man, bman = pr.get("manifest", {}), base.get("manifest", {})
    want = (man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want:
        problems.append(f"{len(rows)} rows, manifest says {want}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    if len(set(keys)) != len(keys):
        problems.append(f"{len(keys) - len(set(keys))} duplicated (item, seed) row(s)")
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if set(keys) != base_keys:
        problems.append(f"(item, seed) set differs from baseline: {len(base_keys - set(keys))} missing, "
                        f"{len(set(keys) - base_keys)} extra")
    if (man.get("items"), sorted(man.get("seeds") or [])) != (bman.get("items"), sorted(bman.get("seeds") or [])):
        problems.append("manifest items/seeds differ from baseline")
    # 4. slice tags are derived from labels: they may not move between runs
    base_slices = {r.get("item_id"): sorted(r.get("slices") or []) for r in base_rows}
    moved = sorted({r.get("item_id") for r in rows
                    if r.get("item_id") in base_slices and sorted(r.get("slices") or []) != base_slices[r.get("item_id")]})
    if moved:
        problems.append(f"slice tags changed vs baseline for {moved}")
    # 5. the reported metrics must be the ones the rows produce (catches hand-edited numbers)
    if rows and not missing:
        no_cost = any("cost" not in r for r in rows)
        ks = set(spec.get("pass_k") or []) | set((base_spec or {}).get("pass_k") or [])
        ks |= {int(m.rsplit("_", 1)[1]) for m in (pr.get("metrics") or {})
               if re.fullmatch(r"pass_(?:at|hat)_\d+", m)}
        again = aggregate([{"cost": 0.0, **r} for r in rows], [m for m in graded if m in rows[0]],
                          k_values=sorted(k for k in ks if 0 < k <= len(man.get("seeds") or [])))
        for mid, v in (pr.get("metrics") or {}).items():
            w = None if (no_cost and mid == "cost_per_success") else again.get(mid)
            if isinstance(v, (int, float)) and isinstance(w, (int, float)) and not (
                    math.isfinite(float(w)) and abs(float(v) - float(w)) <= 1e-3):
                problems.append(f"metric {mid}={v} but rows give {w}")
    # 6. ratchet: on the same eval-set version thresholds may only get stricter
    if base_spec is not None and _same_eval_set(spec, base_spec):
        problems += _ratchet(spec, base_spec)
    return problems


def _same_eval_set(spec: dict, base_spec: dict) -> bool:
    if spec.get("eval_set_version") == base_spec.get("eval_set_version") or spec.get("eval_set") == base_spec.get("eval_set"):
        return True
    a, b = Path(str(spec.get("eval_set"))), Path(str(base_spec.get("eval_set")))
    return a.is_file() and b.is_file() and a.read_bytes() == b.read_bytes()


def _looser(th: dict, bth: dict) -> list[str]:
    out = []
    if "max" in bth and ("max" not in th or th["max"] > bth["max"]):
        out.append(f"max {bth['max']} -> {th.get('max')}")
    if "min" in bth and ("min" not in th or th["min"] < bth["min"]):
        out.append(f"min {bth['min']} -> {th.get('min')}")
    if "max_increase" in bth and ("max_increase" not in th or th["max_increase"] > bth["max_increase"]):
        out.append(f"max_increase {bth['max_increase']} -> {th.get('max_increase')}")
    if bth.get("no_significant_drop") and not th.get("no_significant_drop"):
        out.append("no_significant_drop removed")
    return out


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    problems = []
    now = {m["id"]: m for m in spec.get("metrics") or []}
    for bm in base_spec.get("metrics") or []:
        m = now.get(bm["id"])
        if m is None:
            problems.append(f"RATCHET metric {bm['id']} removed")
            continue
        if bm.get("blocking") and not m.get("blocking"):
            problems.append(f"RATCHET metric {bm['id']} no longer blocking")
        problems += [f"RATCHET {bm['id']} {d}" for d in _looser(m.get("threshold") or {}, bm.get("threshold") or {})]
    bb, b = base_spec.get("bootstrap") or {}, spec.get("bootstrap") or {}
    if b.get("n_resamples", 1000) < bb.get("n_resamples", 1000):
        problems.append(f"RATCHET bootstrap n_resamples {bb.get('n_resamples')} -> {b.get('n_resamples')}")
    for k in ("rng", "method", "confidence"):
        if k in bb and b.get(k) != bb[k]:
            problems.append(f"RATCHET bootstrap {k} {bb[k]} -> {b.get(k)}")
    missing_k = set(base_spec.get("pass_k") or []) - set(spec.get("pass_k") or [])
    if missing_k:
        problems.append(f"RATCHET pass_k dropped {sorted(missing_k)}")
    now_sl = {(x["name"], x["metric"]): x for x in spec.get("slices") or []}
    for bs in base_spec.get("slices") or []:
        x, sid = now_sl.get((bs["name"], bs["metric"])), f"slice:{bs['name']}/{bs['metric']}"
        if x is None:
            problems.append(f"RATCHET {sid} removed")
            continue
        if bs.get("blocking") and not x.get("blocking"):
            problems.append(f"RATCHET {sid} no longer blocking")
        problems += [f"RATCHET {sid} {d}" for d in _looser(x, bs)]
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric, sid = sl["name"], sl["metric"], f"slice:{sl['name']}/{sl['metric']}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        val, verdict, note = None, "ok", ""
        if not a:
            verdict, note = "fail", "no items in slice"   # an empty slice cannot vouch for anything
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            if sl.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}] n={len(keys)}"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = "ok" if verdict == "ok" else ("BLOCK" if sl.get("blocking") else "warn")
        th = {k: sl[k] for k in ("min", "no_significant_drop") if k in sl}
        lines.append(f"  {sid:<34} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
