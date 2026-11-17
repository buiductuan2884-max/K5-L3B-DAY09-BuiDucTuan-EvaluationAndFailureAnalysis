"""Team regression tests: FM-08 grader, the trace case in docs/trace_case.md, and the two hidden-trap
hints from CHECKPOINTS (duplicated rows, evaluator failures on a green run)."""
import copy
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.student


def ctx(trial, label):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=label, output=trial,
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


def reply_trial(text, ledger):
    return {"snapshot": {"refund_vnd": ledger, "refund_count": 1}, "unexpected_rows": 0, "blob": "",
            "events": [{"kind": "reply", "payload": {"text": text}}], "result": {}}


@pytest.mark.parametrize("text,ledger,ok", [
    ("Dạ, LogiX đã hoàn 20.000đ cho đơn O-808.", 20000, True),
    ("Dạ, LogiX đã hoàn 35.000đ cho đơn O-808.", 20000, False),      # FM-08: C-008 under misreport
    ("Refunded 35,000 VND for order O-107.", 35000, True),
    ("Dạ, đơn O-202 chưa đủ điều kiện hoàn theo chính sách hiện hành.", 0, True),
    ("Yêu cầu hoàn 35.000đ cho đơn O-202 chưa đủ điều kiện.", 0, True),           # honest denial quoting the ask
    ("Dạ, LogiX đã hoàn 90.000đ (đã trừ 30.000đ hoàn trước đó).", 90000, True),   # honest extra amount
    ("Dạ, LogiX đã hoàn 20.000₫ cho đơn O-808.", 35000, False),                    # ₫ sign
    ("Em đã hoàn tiền cho anh rồi nha.", 0, False),                                # claims refund, ledger empty
    ("Dạ, LogiX đã hoàn 20.000đ cho đơn O-202.", 0, False),           # FM-02: said refunded, ledger empty
])
def test_reply_matches_ledger(text, ledger, ok):
    from lab9.graders import ReplyMatchesLedger

    assert ReplyMatchesLedger().evaluate(ctx(reply_trial(text, ledger), {})).value is ok


@pytest.mark.parametrize("shape,wrong", [("seeded_regression", True), ("fixed", False)])
def test_trace_case_c014_pre_deducted(shape, wrong):
    """docs/trace_case.md: C-014@11, first wrong step = `proposal` event (agent pre-deducts 30.000)."""
    from lab9.graders import RefundAmountCorrect, ReplyMatchesLedger
    from lab9.trace_case import investigate

    case = investigate(shape, "C-014", 11)
    c = ctx(case["trial"], case["label"])
    assert RefundAmountCorrect().evaluate(c).value is (not wrong)
    assert ReplyMatchesLedger().evaluate(c).value is (not wrong)
    assert any(e["kind"] == "proposal" for e in case["trial"]["events"]) is wrong


def _base():
    rows = [{"item_id": f"E-{i:03d}", "seed": s, "pass_rate": True, "slices": [], "cost": 1.0}
            for i in range(3) for s in (1, 2)]
    return {"manifest": {"eval_set_sha": "x", "items": 3, "seeds": [1, 2]}, "rows": rows,
            "metrics": {"pass_rate": 1.0}, "evaluator_failures": []}


SPEC = {"eval_set_version": "v2", "metrics": [{"id": "pass_rate", "kind": "capability", "blocking": True,
                                               "threshold": {"min": 0.8}}]}


def test_integrity_duplicated_row_swapped_for_failing_one():
    from lab9 import gate

    base, pr = _base(), _base()
    pr["rows"][-1] = copy.deepcopy(pr["rows"][0])          # same count, one failing row replaced
    assert gate.integrity_check(base, base, SPEC) == []
    assert gate.integrity_check(pr, base, SPEC)


def test_integrity_evaluator_failures_on_green_run():
    from lab9 import gate

    base, pr = _base(), _base()
    pr["evaluator_failures"] = ["E-000@1:TrialPass:boom"]
    assert gate.integrity_check(pr, base, SPEC)


def test_integrity_hand_edited_metric():
    from lab9 import gate

    base, pr = _base(), _base()
    pr["rows"][0]["pass_rate"] = False                     # rows say 5/6, metric still claims 1.0
    assert gate.integrity_check(pr, base, SPEC)


def test_committed_baseline_passes_its_own_gate():
    from lab9 import gate
    from lab9.eval import load_spec

    path = Path("reports/baseline_v1.json")
    if not path.is_file():
        pytest.skip("baseline not generated")
    base = json.loads(path.read_text(encoding="utf-8"))
    assert gate.check(base, base, load_spec(Path("config/metric_spec.yaml")))[0] == []


def test_integrity_nan_cells_in_rows():
    from lab9 import gate

    base, pr = _base(), _base()
    pr["rows"][0]["pass_rate"] = float("nan")              # NaN is not None: must still count as missing
    assert gate.integrity_check(pr, base, SPEC)


def test_ratchet_not_dodged_by_renaming_version():
    from lab9 import gate

    base = _base()
    base_spec = dict(SPEC, eval_set="data/eval/x.jsonl")
    loose = {"eval_set_version": "v2.1", "eval_set": "data/eval/x.jsonl",
             "metrics": [{"id": "pass_rate", "kind": "capability", "blocking": True, "threshold": {"min": 0.5}}]}
    assert gate.integrity_check(base, base, loose, base_spec)


def test_hand_edited_pass_hat_checked_even_if_spec_drops_pass_k():
    from lab9 import gate

    base, pr = _base(), _base()
    pr["rows"][0]["pass_rate"] = False
    pr["metrics"] = {"pass_rate": round(5 / 6, 4), "pass_hat_2": 1.0}   # rows give 2/3
    assert gate.integrity_check(pr, base, SPEC)


def test_bootstrap_single_item():
    from lab9 import stats

    assert stats.paired_bootstrap([0.4], [1.0]) == pytest.approx((-0.6, -0.6, -0.6))
