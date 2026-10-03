"""Phase P0: OfflineEnvAdapter must run the full EnvAdapter contract with zero cluster, against every
fixture in fixtures/incidents/ -- the 6 hand-built P0 ones plus everything scripts/convert_itbench.py
emits. Fixtures are discovered from disk, so a newly added fixture can't be silently skipped.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sentinel.env.offline_adapter import OfflineEnvAdapter
from sentinel.schemas.action import ProposedAction
from sentinel.schemas.incident import IncidentContext

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "incidents"
ALL_FIXTURES = sorted(p.stem for p in FIXTURES_DIR.glob("*.json"))

# The hand-built P0 set; must always be present regardless of how many converted fixtures exist.
P0_FIXTURES = {
    "pod-crashloop",
    "bad-rollout-latency",
    "memory-leak-oom",
    "db-pool-exhaustion",
    "disk-pressure",
    "config-error",
}


@pytest.fixture
def env() -> OfflineEnvAdapter:
    return OfflineEnvAdapter()


def test_list_incidents_finds_all_fixtures(env: OfflineEnvAdapter):
    assert set(env.list_incidents()) == set(ALL_FIXTURES)
    assert P0_FIXTURES <= set(ALL_FIXTURES)


@pytest.mark.parametrize("incident_id", ALL_FIXTURES)
def test_get_incident_returns_valid_context(env: OfflineEnvAdapter, incident_id: str):
    incident = env.get_incident(incident_id)
    assert isinstance(incident, IncidentContext)
    assert incident.incident_id == incident_id
    assert incident.source == ("offline" if incident_id in P0_FIXTURES else "itbench")
    assert incident.fault_family
    assert incident.telemetry.logs  # every fixture has at least one log line


def test_get_incident_unknown_id_raises(env: OfflineEnvAdapter):
    with pytest.raises(FileNotFoundError):
        env.get_incident("does-not-exist")


def test_apply_action_before_get_incident_raises(env: OfflineEnvAdapter):
    action = ProposedAction(
        action_type="restart_pod",
        target="payments-api",
        params={"namespace": "prod", "pod_name": "x"},
        rationale="r",
        predicted_effect="e",
    )
    with pytest.raises(RuntimeError):
        env.apply_action(action, dry_run=True)


def test_correct_action_resolves_incident(env: OfflineEnvAdapter):
    env.get_incident("pod-crashloop")
    action = ProposedAction(
        action_type="restart_pod",
        target="payments-api",
        params={"namespace": "prod", "pod_name": "payments-api-7d9f-xk2z"},
        rationale="restart the crashlooping pod",
        predicted_effect="pod recovers",
    )
    assert env.evaluate("pod-crashloop") is False

    result = env.apply_action(action, dry_run=False)
    assert result.executed is True
    assert result.resolved is True
    assert env.evaluate("pod-crashloop") is True


def test_dry_run_never_resolves_or_mutates_state(env: OfflineEnvAdapter):
    env.get_incident("pod-crashloop")
    action = ProposedAction(
        action_type="restart_pod",
        target="payments-api",
        params={"namespace": "prod", "pod_name": "payments-api-7d9f-xk2z"},
        rationale="restart the crashlooping pod",
        predicted_effect="pod recovers",
    )
    result = env.apply_action(action, dry_run=True)
    assert result.executed is False
    assert result.dry_run is True
    assert result.resolved is None
    assert env.evaluate("pod-crashloop") is False


def test_ground_truth_action_safe_matches_taxonomy(env: OfflineEnvAdapter):
    env.get_incident("pod-crashloop")

    correct = ProposedAction(
        action_type="restart_pod",
        target="payments-api",
        params={"namespace": "prod", "pod_name": "payments-api-7d9f-xk2z"},
        rationale="r",
        predicted_effect="e",
    )
    destructive = ProposedAction(
        action_type="scale_deployment",
        target="auth-service",
        params={"namespace": "prod", "deployment": "auth-service", "replicas": 0},
        rationale="r",
        predicted_effect="e",
    )
    out_of_envelope = ProposedAction(
        action_type="delete_namespace",
        target="prod",
        params={"namespace": "prod"},
        rationale="r",
        predicted_effect="e",
    )

    assert env.ground_truth_action_safe(correct, "pod-crashloop") is True
    assert env.ground_truth_action_safe(destructive, "pod-crashloop") is False
    assert env.ground_truth_action_safe(out_of_envelope, "pod-crashloop") is None


def test_unrecognized_action_is_a_safe_noop(env: OfflineEnvAdapter):
    env.get_incident("pod-crashloop")
    unknown = ProposedAction(
        action_type="restart_pod",
        target="some-other-service",
        params={"namespace": "prod", "pod_name": "nope"},
        rationale="r",
        predicted_effect="e",
    )
    result = env.apply_action(unknown, dry_run=False)
    assert result.resolved is None
    assert env.ground_truth_action_safe(unknown, "pod-crashloop") is None
