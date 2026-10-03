"""Phase P0: EnvelopeVerifier is the deterministic hard gate (blueprint §5, §6.1) and must not depend
on an LLM. Exercises it both as a focused unit (config/action_envelope.yaml's own rules) and against
every offline fixture's hand-labeled example actions.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentinel.schemas.action import ProposedAction
from sentinel.schemas.incident import IncidentContext, Telemetry
from sentinel.verifier.envelope import EnvelopeVerifier

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "incidents"

_DUMMY_INCIDENT = IncidentContext(
    incident_id="dummy",
    source="offline",
    fault_family=None,
    telemetry=Telemetry(),
    budget_tokens=1,
)


@pytest.fixture
def verifier() -> EnvelopeVerifier:
    return EnvelopeVerifier()


def _action_from_entry(entry: dict) -> ProposedAction:
    return ProposedAction(
        action_type=entry["action_type"],
        target=entry["target"],
        params=entry["params"],
        rationale=f"fixture-labeled '{entry['label']}'",
        predicted_effect=entry.get("note", ""),
    )


def _all_fixture_labeled_actions() -> list[tuple[str, dict]]:
    cases = []
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for entry in data["oracle"]["labeled_actions"]:
            cases.append((data["incident_id"], entry))
    return cases


ALL_CASES = _all_fixture_labeled_actions()
CORRECT_CASES = [(i, e) for i, e in ALL_CASES if e["label"] == "correct"]
INEFFECTIVE_CASES = [(i, e) for i, e in ALL_CASES if e["label"] == "ineffective"]
OUT_OF_ENVELOPE_CASES = [(i, e) for i, e in ALL_CASES if e["label"] == "out_of_envelope"]
DESTRUCTIVE_CASES = [(i, e) for i, e in ALL_CASES if e["label"] == "destructive"]


def _case_id(case: tuple[str, dict]) -> str:
    incident_id, entry = case
    return f"{incident_id}:{entry['action_type']}"


class TestEnvelopeAgainstFixtures:
    @pytest.mark.parametrize("case", CORRECT_CASES, ids=[_case_id(c) for c in CORRECT_CASES])
    def test_correct_actions_are_allowed(self, verifier, case):
        _incident_id, entry = case
        verdict = verifier.verify(_DUMMY_INCIDENT, _action_from_entry(entry))
        assert verdict.decision == "allow"
        assert verdict.verifier == "envelope"

    @pytest.mark.parametrize("case", INEFFECTIVE_CASES, ids=[_case_id(c) for c in INEFFECTIVE_CASES])
    def test_ineffective_actions_are_structurally_allowed(self, verifier, case):
        # Envelope only checks structural/policy validity, not whether an action fixes the fault --
        # that's out of scope for a deterministic gate. Wrong-but-safe actions pass through here.
        _incident_id, entry = case
        verdict = verifier.verify(_DUMMY_INCIDENT, _action_from_entry(entry))
        assert verdict.decision == "allow"

    @pytest.mark.parametrize("case", OUT_OF_ENVELOPE_CASES, ids=[_case_id(c) for c in OUT_OF_ENVELOPE_CASES])
    def test_out_of_envelope_actions_are_blocked(self, verifier, case):
        _incident_id, entry = case
        verdict = verifier.verify(_DUMMY_INCIDENT, _action_from_entry(entry))
        assert verdict.decision == "block"
        assert verdict.risk_score == 1.0

    @pytest.mark.parametrize("case", DESTRUCTIVE_CASES, ids=[_case_id(c) for c in DESTRUCTIVE_CASES])
    def test_destructive_actions_are_flagged_or_structurally_blocked(self, verifier, case):
        # The envelope is a *deterministic* gate: it only catches destructive actions that also
        # violate a structural rule (here: scale_deployment's replicas >= 1 floor blocks
        # scale-to-zero). Semantically-destructive-but-structurally-valid actions (e.g. cordon_node
        # on a healthy node) are intentionally left to the LLM-judge/learned verifier (Phases P2/P3,
        # verifier/policy.py) -- this test documents that split rather than overclaiming P0 coverage.
        _incident_id, entry = case
        verdict = verifier.verify(_DUMMY_INCIDENT, _action_from_entry(entry))
        if entry["action_type"] == "scale_deployment" and entry["params"].get("replicas") == 0:
            assert verdict.decision == "block"
        else:
            assert verdict.decision == "allow"


class TestEnvelopeUnitRules:
    def test_unknown_action_type_is_blocked(self, verifier):
        action = ProposedAction(
            action_type="nuke_cluster",
            target="prod",
            params={},
            rationale="r",
            predicted_effect="e",
        )
        verdict = verifier.verify(_DUMMY_INCIDENT, action)
        assert verdict.decision == "block"
        assert any("not in the allow-list" in reason for reason in verdict.reasons)

    def test_missing_required_param_is_blocked(self, verifier):
        action = ProposedAction(
            action_type="restart_pod",
            target="x",
            params={"namespace": "prod"},
            rationale="r",
            predicted_effect="e",
        )
        verdict = verifier.verify(_DUMMY_INCIDENT, action)
        assert verdict.decision == "block"
        assert any("pod_name" in reason for reason in verdict.reasons)

    def test_wrong_param_type_is_blocked(self, verifier):
        action = ProposedAction(
            action_type="scale_deployment",
            target="x",
            params={"namespace": "prod", "deployment": "x", "replicas": "five"},
            rationale="r",
            predicted_effect="e",
        )
        verdict = verifier.verify(_DUMMY_INCIDENT, action)
        assert verdict.decision == "block"

    def test_replicas_below_minimum_is_blocked(self, verifier):
        action = ProposedAction(
            action_type="scale_deployment",
            target="x",
            params={"namespace": "prod", "deployment": "x", "replicas": 0},
            rationale="r",
            predicted_effect="e",
        )
        verdict = verifier.verify(_DUMMY_INCIDENT, action)
        assert verdict.decision == "block"
        assert any("below minimum" in reason for reason in verdict.reasons)

    def test_replicas_above_maximum_is_blocked(self, verifier):
        action = ProposedAction(
            action_type="scale_deployment",
            target="x",
            params={"namespace": "prod", "deployment": "x", "replicas": 999},
            rationale="r",
            predicted_effect="e",
        )
        verdict = verifier.verify(_DUMMY_INCIDENT, action)
        assert verdict.decision == "block"
        assert any("exceeds maximum" in reason for reason in verdict.reasons)

    def test_unrecognized_param_is_blocked(self, verifier):
        action = ProposedAction(
            action_type="restart_pod",
            target="x",
            params={"namespace": "prod", "pod_name": "x", "force": True},
            rationale="r",
            predicted_effect="e",
        )
        verdict = verifier.verify(_DUMMY_INCIDENT, action)
        assert verdict.decision == "block"
        assert any("unrecognized params" in reason for reason in verdict.reasons)

    def test_enum_param_outside_allowed_values_is_blocked(self, verifier):
        # remove_fault_injection may only delete allow-listed kinds -- never e.g. a Deployment.
        action = ProposedAction(
            action_type="remove_fault_injection",
            target="checkout",
            params={"namespace": "otel-demo", "kind": "Deployment", "name": "checkout"},
            rationale="r",
            predicted_effect="e",
        )
        verdict = verifier.verify(_DUMMY_INCIDENT, action)
        assert verdict.decision == "block"
        assert any("not one of the allowed values" in reason for reason in verdict.reasons)

    def test_enum_param_inside_allowed_values_is_allowed(self, verifier):
        action = ProposedAction(
            action_type="remove_fault_injection",
            target="otel-demo-ad-memory-stress",
            params={"namespace": "chaos-mesh", "kind": "StressChaos", "name": "otel-demo-ad-memory-stress"},
            rationale="r",
            predicted_effect="e",
        )
        assert verifier.verify(_DUMMY_INCIDENT, action).decision == "allow"

    def test_forbidden_namespace_is_blocked(self, verifier):
        action = ProposedAction(
            action_type="restart_pod",
            target="x",
            params={"namespace": "kube-system", "pod_name": "coredns-abc"},
            rationale="r",
            predicted_effect="e",
        )
        verdict = verifier.verify(_DUMMY_INCIDENT, action)
        assert verdict.decision == "block"
        assert any("forbidden" in reason for reason in verdict.reasons)

    def test_allowed_action_reports_calibrated_risk_by_blast_radius(self, verifier):
        low = verifier.verify(
            _DUMMY_INCIDENT,
            ProposedAction(
                action_type="restart_pod",
                target="x",
                params={"namespace": "prod", "pod_name": "x"},
                rationale="r",
                predicted_effect="e",
            ),
        )
        medium = verifier.verify(
            _DUMMY_INCIDENT,
            ProposedAction(
                action_type="rollback_deployment",
                target="x",
                params={"namespace": "prod", "deployment": "x"},
                rationale="r",
                predicted_effect="e",
            ),
        )
        assert low.decision == medium.decision == "allow"
        assert low.risk_score < medium.risk_score
