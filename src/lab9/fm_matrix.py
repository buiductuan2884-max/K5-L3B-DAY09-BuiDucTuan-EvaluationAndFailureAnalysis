"""Evidence for docs/failure_taxonomy.md: turn on ONE bug switch at a time and see which claim breaks.

    python -m lab9.fm_matrix                 # prints the matrix, writes reports/fm_matrix.json

Each switch is the `fixed` agent plus one bug from lab9.variant_agent.BUGS, run on all 14 public
claims at seed 11 (no flaky modulator). A cell is "caught" when a grader in lab9.graders fires,
"lab8_only" when Lab 8's own grader is the one that notices, "missed" when nobody does.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from lab8.console import utf8_stdio
from lab8.db import load_json, load_jsonl
from lab8.shapes import SHAPES
from lab9.eval import WORLD, make_task
from lab9.graders import GRADERS
from lab9.variant_agent import make_shape

# row name -> (bug switch, event kind that is the first wrong step); FM-04 has two mechanisms
SWITCHES = {
    "FM-01": ("leaky_trace", "debug_claim_row"),
    "FM-02": ("ignore_denied", "reply"),
    "FM-03": ("ticket_trust", "model_override"),
    "FM-04": ("sum_parts", "proposal"),
    "FM-04/round": ("round_down", "proposal"),
    "FM-05": ("pre_deducted", "proposal"),
    "FM-06": ("stale_clause", "quote"),
    "FM-07": ("sibling_refund", "batch_refund"),
    "FM-08": ("misreport", "reply"),
}
SAFETY = {"secret_leak", "approval_bypass"}


def grade(trial: dict, label: dict) -> dict[str, bool]:
    """metric -> True when that grader says this trial is BAD."""
    from pydantic_evals.evaluators import EvaluatorContext
    ctx = EvaluatorContext(name="m", inputs={}, metadata=None, expected_output=label, output=trial,
                           duration=0.0, _span_tree=None, attributes={}, metrics={})
    out = {}
    for mid, cls in GRADERS.items():
        v = bool(cls().evaluate(ctx).value)
        out[mid] = v if mid in SAFETY else not v
    return out


def run(seed: int = 11) -> dict:
    claims = load_jsonl(Path("data/public_claims.jsonl"))
    labels = {c["claim_id"]: c["expected"] for c in claims}
    world, result = load_json(WORLD), {}
    for fm, (bug, step) in SWITCHES.items():
        name = f"only_{bug}"
        SHAPES[name] = make_shape(name, {"no_override", bug})
        with tempfile.TemporaryDirectory(prefix="lab9-fm-", ignore_cleanup_errors=True) as tmp:
            task = make_task(name, world, claims, labels, Path(tmp))
            for c in claims:
                t = task({"claim_id": c["claim_id"], "seed": seed})
                bad = grade(t, labels[c["claim_id"]])
                fired = sorted(m for m, b in bad.items() if b)
                kinds = [e.get("kind") for e in t["events"]]
                reply = next((e["payload"].get("text") for e in t["events"] if e.get("kind") == "reply"), "")
                result.setdefault(fm, {"bug": bug, "first_wrong_step": step, "claims": {}})["claims"][c["claim_id"]] = {
                    "fired": fired, "lab8_pass": t["lab8_pass"], "lab8_reason": t["lab8_reason"],
                    "ledger_vnd": t["snapshot"].get("refund_vnd"), "label_vnd": labels[c["claim_id"]].get("refund_vnd"),
                    "status": t["result"].get("status"), "label_status": labels[c["claim_id"]].get("status"),
                    "reply": reply, "events": kinds,
                    "first_wrong_step": (kinds.index(step) + 1) if fired and step in kinds else None}
    return {"seed": seed, "matrix": result}


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.fm_matrix")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", default="reports/fm_matrix.json")
    args = ap.parse_args(argv)
    rep = run(args.seed)
    for fm, row in rep["matrix"].items():
        hits = {cid: c["fired"] for cid, c in row["claims"].items() if c["fired"]}
        lab8_blind = [cid for cid, c in row["claims"].items() if c["fired"] and c["lab8_pass"]]
        print(f"{fm} {row['bug']:<15} breaks {len(hits):>2}/14: {', '.join(hits)}"
              + (f"   (Lab 8 grader blind on {', '.join(lab8_blind)})" if lab8_blind else ""))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
