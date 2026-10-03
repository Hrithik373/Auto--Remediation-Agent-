"""Phase P4: the canonical metric definitions (blueprint §7) on hand-built RunRecords."""

from __future__ import annotations

import pytest

from sentinel.eval.metrics import (
    bad_action_prevented_rate,
    false_block_rate,
    mean_steps_to_mitigation,
    net_safe_resolutions,
    prevention_partition,
    resolution_rate,
    summarize,
    unlabeled_step_rate,
    unsafe_execution_rate,
)
from sentinel.schemas.action import ExecutionResult, ProposedAction
from sentinel.schemas.run import RunRecord, StepRecord
from sentinel.schemas.verdict import LayerVerdict, Verdict

ACTION = ProposedAction(action_type="restart_pod", target="x", params={}, rationale="r", predicted_effect="e")


def _step(label, decision, envelope="allow", executed=None):
    layers = [
        LayerVerdict(verifier="envelope", decision=envelope),
        LayerVerdict(verifier="llm_judge", decision="skipped"),
        LayerVerdict(
            verifier="learned", decision="block" if envelope == "allow" and decision != "allow" else "skipped"
        ),
    ]
    result = ExecutionResult(executed=True, dry_run=False) if (executed or decision == "allow") else None
    return StepRecord(
        step_idx=0,
        proposed=ACTION,
        tokens=0,
        latency_ms=1.0,
        ground_truth_label=label,
        result=result,
        verdict=Verdict(decision=decision, risk_score=0.5, verifier="combined", layers=layers),
    )


def _run(steps, resolved=False, unsafe=False):
    return RunRecord(
        incident_id="i",
        seed=0,
        config_hash="h",
        steps=steps,
        final_resolved=resolved,
        unsafe_action_reached_exec=unsafe,
        mttm_ms=10.0 if resolved else None,
    )


RUNS = [
    _run([_step("destructive", "block", envelope="block")]),  # caught by envelope
    _run([_step("destructive", "block"), _step("correct", "allow")], resolved=True),  # caught by secondary
    _run([_step("destructive", "allow"), _step("correct", "allow")], resolved=True, unsafe=True),  # missed
    _run([_step("correct", "block")]),  # false block
    _run([_step(None, "allow")]),  # unlabeled step
]


def test_resolution_rate():
    assert resolution_rate(RUNS) == pytest.approx(2 / 5)


def test_bad_action_prevented_rate():
    assert bad_action_prevented_rate(RUNS) == pytest.approx(2 / 3)


def test_false_block_rate():
    assert false_block_rate(RUNS) == pytest.approx(1 / 3)


def test_net_safe_resolutions():
    assert net_safe_resolutions(RUNS) == pytest.approx(
        1 / 5
    )  # run 3 resolved but executed a destructive action


def test_unsafe_execution_and_steps_to_mitigation():
    assert unsafe_execution_rate(RUNS) == pytest.approx(1 / 5)
    assert mean_steps_to_mitigation(RUNS) == 2


def test_prevention_partition_sums_to_one_and_attributes_layers():
    partition = prevention_partition(RUNS)
    assert partition == pytest.approx(
        {"caught_by_envelope": 1 / 3, "caught_by_secondary_only": 1 / 3, "missed": 1 / 3}
    )


def test_empty_denominators_are_none_not_zero():
    only_safe = [_run([_step("ineffective", "allow")])]
    assert bad_action_prevented_rate(only_safe) is None
    assert false_block_rate(only_safe) is None
    assert prevention_partition(only_safe) is None
    assert resolution_rate([]) is None


def test_unlabeled_steps_are_counted_and_excluded():
    assert unlabeled_step_rate(RUNS) == pytest.approx(1 / 7)  # 1 + 2 + 2 + 1 + 1 steps
    assert summarize(RUNS)["n_steps"] == 7
