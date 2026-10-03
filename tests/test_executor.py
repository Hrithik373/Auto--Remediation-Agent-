"""Phase P1: the executor enforces CLAUDE.md's golden rules in code."""

from __future__ import annotations

import pytest

from sentinel.env.offline_adapter import OfflineEnvAdapter
from sentinel.executor.executor import ExecutionRefused, Executor
from sentinel.executor.rollback import plan_rollback
from sentinel.schemas.action import ExecutionResult, ProposedAction
from sentinel.schemas.verdict import Verdict

CORRECT = ProposedAction(
    action_type="restart_pod",
    target="payments-api",
    params={"namespace": "prod", "pod_name": "payments-api-7d9f-xk2z"},
    rationale="r",
    predicted_effect="e",
)
ALLOW = Verdict(decision="allow", risk_score=0.1, reasons=["ok"], verifier="combined")
BLOCK = Verdict(decision="block", risk_score=0.9, reasons=["no"], verifier="combined")


@pytest.fixture
def env() -> OfflineEnvAdapter:
    env = OfflineEnvAdapter()
    env.get_incident("pod-crashloop")
    return env


def test_dry_run_needs_no_verdict_and_changes_nothing(env):
    executor = Executor(env)
    result = executor.run(CORRECT, dry_run=True)
    assert result.dry_run and not result.executed
    assert env.evaluate("pod-crashloop") is False
    assert executor.log == [(CORRECT, result)]


def test_auto_execute_defaults_to_false(env):
    executor = Executor(env)
    assert executor.auto_execute is False
    with pytest.raises(ExecutionRefused, match="auto_execute"):
        executor.run(CORRECT, verdict=ALLOW, dry_run=False)


@pytest.mark.parametrize("verdict", [None, BLOCK, BLOCK.model_copy(update={"decision": "revise"})])
def test_real_apply_requires_allow_verdict(env, verdict):
    with pytest.raises(ExecutionRefused, match="allow"):
        Executor(env, auto_execute=True).run(CORRECT, verdict=verdict, dry_run=False)
    assert env.evaluate("pod-crashloop") is False


def test_real_apply_with_allow_and_flag_resolves(env):
    result = Executor(env, auto_execute=True).run(CORRECT, verdict=ALLOW, dry_run=False)
    assert result.executed and result.resolved
    assert env.evaluate("pod-crashloop") is True


def test_env_failure_is_recorded_not_raised():
    fresh = OfflineEnvAdapter()  # no get_incident() -> apply_action raises inside the env
    result = Executor(fresh).run(CORRECT, dry_run=True)
    assert result.executed is False and "RuntimeError" in result.error


def test_rollback_plans_inverse_only_for_executed_reversible_actions():
    flag = ProposedAction(
        action_type="toggle_feature_flag",
        target="flagd-config",
        params={"namespace": "otel-demo", "configmap": "flagd-config", "flag": "adFailure", "enabled": False},
        rationale="r",
        predicted_effect="e",
    )
    executed = ExecutionResult(executed=True, dry_run=False)
    inverse = plan_rollback(flag, executed)
    assert inverse is not None and inverse.params["enabled"] is True
    assert plan_rollback(flag, ExecutionResult(executed=False, dry_run=True)) is None
    assert plan_rollback(CORRECT, executed) is None  # no inverse fully determined by the action
