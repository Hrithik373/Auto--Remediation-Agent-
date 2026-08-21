"""Phase P0: the core Pydantic contracts (blueprint §4) are frozen and must validate correctly."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sentinel.schemas.action import ExecutionResult, ProposedAction
from sentinel.schemas.incident import IncidentContext, Telemetry
from sentinel.schemas.run import RunRecord, StepRecord
from sentinel.schemas.verdict import Verdict


def _telemetry(**overrides) -> Telemetry:
    defaults = dict(
        logs=["boot ok"],
        metrics={"cpu_util_pct": [10.0, 20.0]},
        traces=[{"span": "x", "status": "ok"}],
        topology={"services": ["a", "b"], "edges": [["a", "b"]]},
        alerts=[{"name": "Test", "severity": "low"}],
    )
    defaults.update(overrides)
    return Telemetry(**defaults)


def _incident(**overrides) -> IncidentContext:
    defaults = dict(
        incident_id="unit-test-incident",
        source="offline",
        fault_family="crashloop",
        telemetry=_telemetry(),
        budget_tokens=8000,
    )
    defaults.update(overrides)
    return IncidentContext(**defaults)


def _action(**overrides) -> ProposedAction:
    defaults = dict(
        action_type="restart_pod",
        target="payments-api",
        params={"namespace": "prod", "pod_name": "payments-api-abc"},
        rationale="pod is crashlooping on startup",
        predicted_effect="pod restarts and recovers",
    )
    defaults.update(overrides)
    return ProposedAction(**defaults)


class TestTelemetryAndIncidentContext:
    def test_telemetry_defaults_are_empty(self):
        t = Telemetry()
        assert t.logs == []
        assert t.metrics == {}
        assert t.traces == []
        assert t.topology == {}
        assert t.alerts == []

    def test_incident_context_round_trip(self):
        incident = _incident()
        restored = IncidentContext.model_validate_json(incident.model_dump_json())
        assert restored == incident

    def test_incident_context_requires_nonempty_id(self):
        with pytest.raises(ValidationError):
            _incident(incident_id="")

    def test_incident_context_requires_positive_budget(self):
        with pytest.raises(ValidationError):
            _incident(budget_tokens=0)

    def test_incident_context_source_is_constrained(self):
        with pytest.raises(ValidationError):
            _incident(source="not-a-real-source")

    def test_fault_family_is_optional(self):
        incident = _incident(fault_family=None)
        assert incident.fault_family is None


class TestActionSchemas:
    def test_proposed_action_round_trip(self):
        action = _action()
        restored = ProposedAction.model_validate_json(action.model_dump_json())
        assert restored == action

    def test_proposed_action_requires_nonempty_type_and_target(self):
        with pytest.raises(ValidationError):
            _action(action_type="")
        with pytest.raises(ValidationError):
            _action(target="")

    def test_execution_result_resolved_defaults_none(self):
        result = ExecutionResult(executed=False, dry_run=True)
        assert result.resolved is None
        assert result.side_effects == []
        assert result.error is None


class TestVerdict:
    def test_verdict_valid(self):
        verdict = Verdict(decision="allow", risk_score=0.1, reasons=["ok"], verifier="envelope")
        assert verdict.decision == "allow"

    def test_verdict_rejects_unknown_decision(self):
        with pytest.raises(ValidationError):
            Verdict(decision="maybe", risk_score=0.1, reasons=[], verifier="envelope")

    @pytest.mark.parametrize("risk_score", [-0.01, 1.01])
    def test_verdict_risk_score_bounds(self, risk_score):
        with pytest.raises(ValidationError):
            Verdict(decision="block", risk_score=risk_score, reasons=[], verifier="envelope")


class TestRunSchemas:
    def test_step_and_run_record_round_trip(self):
        step = StepRecord(
            step_idx=0,
            proposed=_action(),
            verdict=Verdict(decision="allow", risk_score=0.1, reasons=["ok"], verifier="envelope"),
            result=ExecutionResult(executed=True, dry_run=True, resolved=True),
            tokens=123,
            latency_ms=45.6,
        )
        run = RunRecord(
            incident_id="unit-test-incident",
            seed=0,
            config_hash="deadbeef",
            steps=[step],
            final_resolved=True,
            unsafe_action_reached_exec=False,
            mttm_ms=1000.0,
            total_tokens=123,
            total_cost_usd=0.01,
        )
        restored = RunRecord.model_validate_json(run.model_dump_json())
        assert restored == run

    def test_run_record_defaults(self):
        run = RunRecord(
            incident_id="x",
            seed=0,
            config_hash="h",
            final_resolved=False,
            unsafe_action_reached_exec=False,
        )
        assert run.steps == []
        assert run.total_tokens == 0
        assert run.total_cost_usd == 0.0
