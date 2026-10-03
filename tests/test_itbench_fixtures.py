"""Integrity checks on fixtures emitted by scripts/convert_itbench.py (docs/tasks/itbench_converter_spec.md
§5). These read only the committed JSON -- they never need the raw ITBench download.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentinel.verifier.envelope import EnvelopeVerifier

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "incidents"
ITBENCH_FIXTURES = sorted(FIXTURES_DIR.glob("itbench-sre-scenario-*.json"))
MAX_FIXTURE_BYTES = 300 * 1024  # "a few hundred KB": raw telemetry must not leak through
PROVENANCES = {"itbench_derived", "converter_synthesized", "human_reviewed"}
LABELS = {"correct", "ineffective", "destructive", "out_of_envelope"}

pytestmark = pytest.mark.skipif(not ITBENCH_FIXTURES, reason="no converted ITBench fixtures present")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", ITBENCH_FIXTURES, ids=lambda p: p.stem)
class TestITBenchFixture:
    def test_incident_id_matches_filename_and_source(self, path):
        data = _load(path)
        assert data["incident_id"] == path.stem
        assert data["source"] == "itbench"

    def test_size_is_capped(self, path):
        assert path.stat().st_size < MAX_FIXTURE_BYTES

    def test_every_labeled_action_has_provenance_and_valid_label(self, path):
        for entry in _load(path)["oracle"]["labeled_actions"]:
            assert entry["provenance"] in PROVENANCES
            assert entry["label"] in LABELS
            assert isinstance(entry["needs_review"], bool)
            assert entry["action_type"]  # unmapped text goes to unmapped_recommendations, never here

    def test_ground_truth_answer_does_not_leak_into_telemetry(self, path):
        # root_cause flags and propagation prose describe the answer; the agent sees telemetry only.
        data = _load(path)
        telemetry = json.dumps(data["telemetry"])
        assert "root_cause" not in telemetry
        for prop in data["itbench"]["propagations"]:
            for prose in (prop.get("condition"), prop.get("effect")):
                if prose and len(prose) > 25:
                    assert prose not in telemetry

    def test_no_target_is_both_correct_and_ineffective(self, path):
        # e.g. ITBench recommends "restart cart" -> a synthesized "restart cart pod = ineffective" would
        # contradict the benchmark's own ground truth.
        entries = _load(path)["oracle"]["labeled_actions"]
        correct = {e["target"] for e in entries if e["label"] == "correct"}
        ineffective = {e["target"] for e in entries if e["label"] == "ineffective"}
        assert not correct & ineffective

    def test_resolvable_flag_matches_correct_actions(self, path):
        oracle = _load(path)["oracle"]
        has_correct = any(e["label"] == "correct" for e in oracle["labeled_actions"])
        assert oracle["resolvable_within_envelope"] == has_correct

    def test_correct_actions_pass_the_envelope(self, path):
        # A "correct" label the hard gate would block is a broken fixture (or a broken envelope).
        from sentinel.schemas.action import ProposedAction
        from sentinel.schemas.incident import IncidentContext, Telemetry

        verifier = EnvelopeVerifier()
        incident = IncidentContext(incident_id="x", source="itbench", telemetry=Telemetry(), budget_tokens=1)
        for entry in _load(path)["oracle"]["labeled_actions"]:
            if entry["label"] != "correct":
                continue
            action = ProposedAction(
                action_type=entry["action_type"],
                target=entry["target"],
                params=entry["params"],
                rationale="r",
                predicted_effect="e",
            )
            verdict = verifier.verify(incident, action)
            assert verdict.decision == "allow", (entry, verdict.reasons)


def test_at_least_most_scenarios_are_resolvable_within_envelope():
    resolvable = [p for p in ITBENCH_FIXTURES if _load(p)["oracle"]["resolvable_within_envelope"]]
    assert len(resolvable) >= 0.8 * len(ITBENCH_FIXTURES)
