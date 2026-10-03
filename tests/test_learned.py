"""Phase P3: labeling (augmentation, dataset, review CLI), features, and the learned verifier.

Acceptance (blueprint §8): labeled dataset built and split by incident; the XGBoost verifier reports
AUC + ECE on held-out incidents; both verifiers swappable via config.
"""

from __future__ import annotations

import json
import shutil

import numpy as np
import pytest

from sentinel.env.offline_adapter import OfflineEnvAdapter
from sentinel.labeling.augment import augmented_candidates
from sentinel.labeling.dataset import build_dataset
from sentinel.labeling.oracle_labeler import derive_label_with_provenance
from sentinel.labeling.review_cli import FIXTURES_DIR, review_fixture
from sentinel.schemas.action import ProposedAction
from sentinel.verifier.features import extract_features
from sentinel.verifier.learned import (
    LearnedVerifier,
    expected_calibration_error,
    train_bundle,
    type_only_baseline,
)
from sentinel.verifier.policy import build_policy


@pytest.fixture(scope="module")
def env() -> OfflineEnvAdapter:
    return OfflineEnvAdapter()


@pytest.fixture(scope="module")
def rows(env):
    return build_dataset(env)


@pytest.fixture(scope="module")
def incidents(env):
    return {i: env.get_incident(i) for i in env.list_incidents()}


@pytest.fixture(scope="module")
def bundle(rows, incidents):
    return train_bundle(rows, incidents, seed=0, n_folds=5)


# -- labeling ------------------------------------------------------------------------------------


def test_augmentation_adds_within_type_contrasts(env):
    raw = json.loads((FIXTURES_DIR / "itbench-sre-scenario-4.json").read_text(encoding="utf-8"))
    extra = augmented_candidates(raw)
    flags = {(e["params"]["enabled"], e["label"]) for e in extra if e["action_type"] == "toggle_feature_flag"}
    assert flags == {(True, "destructive"), (False, "ineffective")}
    assert all(e["provenance"] == "rule_augmented" and e["needs_review"] for e in extra)
    assert extra == augmented_candidates(raw)  # deterministic


def test_augmented_restart_never_targets_implicated_services(env):
    for incident_id in env.list_incidents():
        incident = env.get_incident(incident_id)
        alerted = {str(a.get("target")) for a in incident.telemetry.alerts}
        for entry in env.candidate_actions(incident_id):
            if entry.get("rule") in ("R1", "R2"):
                assert entry["target"] not in alerted


def test_labeler_labels_augmented_candidates_with_rule_provenance(env):
    entry = next(e for e in env.candidate_actions("itbench-sre-scenario-4") if e.get("rule") == "R3")
    action = ProposedAction(
        action_type=entry["action_type"],
        target=entry["target"],
        params=entry["params"],
        rationale="r",
        predicted_effect="e",
    )
    assert derive_label_with_provenance(env, action, "itbench-sre-scenario-4") == (
        "destructive",
        "rule_augmented:R3",
    )


def test_dataset_covers_every_incident_with_provenance(env, rows):
    assert {r.incident_id for r in rows} == set(env.list_incidents())
    assert {r.provenance for r in rows} >= {
        "hand_built",
        "itbench_derived",
        "converter_synthesized",
        "rule_augmented",
    }


def test_review_cli_records_human_review(tmp_path):
    path = tmp_path / "fx.json"
    shutil.copy(FIXTURES_DIR / "itbench-sre-scenario-1.json", path)
    # entry 1 is labeled correct (accept it); entry 2 is labeled destructive (relabel -> ineffective)
    answers = iter(["a", "i", "q"])
    tally = review_fixture(path, "tester", ask=lambda _: next(answers), say=lambda _: None)
    assert tally == {"accepted": 1, "relabeled": 1}
    reviewed = [
        e
        for e in json.loads(path.read_text(encoding="utf-8"))["oracle"]["labeled_actions"]
        if e["provenance"] == "human_reviewed"
    ]
    assert len(reviewed) == 2 and all(
        e["reviewed_by"] == "tester" and not e["needs_review"] for e in reviewed
    )
    assert reviewed[1]["label"] == "ineffective" and reviewed[1]["original_label"] == "destructive"
    assert reviewed[1]["original_provenance"] == "converter_synthesized"


# -- features ------------------------------------------------------------------------------------


def test_features_never_see_oracle_or_ids(env, incidents):
    incident = incidents["pod-crashloop"]
    action = ProposedAction(
        action_type="restart_pod",
        target="payments-api",
        params={"namespace": "prod", "pod_name": "x"},
        rationale="r",
        predicted_effect="e",
    )
    feats = extract_features(incident, action)
    assert all(isinstance(v, float) for v in feats.values())
    blinded = incident.model_copy(update={"incident_id": "zzz", "fault_family": None})
    assert extract_features(blinded, action) == feats  # identical without id / fault_family


def test_linkage_features_separate_implicated_from_unrelated_targets(incidents):
    incident = incidents["pod-crashloop"]

    def mk(target: str) -> ProposedAction:
        return ProposedAction(
            action_type="restart_service",
            target=target,
            params={"namespace": "prod", "service": target},
            rationale="r",
            predicted_effect="e",
        )

    assert extract_features(incident, mk("payments-api"))["target_in_alert"] == 1.0
    assert extract_features(incident, mk("auth-service"))["target_in_alert"] == 0.0


# -- learned verifier ----------------------------------------------------------------------------


def test_cross_fitting_never_scores_an_incident_with_a_model_that_saw_it(bundle, rows):
    fold_of = bundle["fold_of"]
    assert set(fold_of) == {r.incident_id for r in rows if r.label != "out_of_envelope"}
    assert len(set(fold_of.values())) == bundle["n_folds"]


def test_held_out_metrics_reported_and_beat_type_only_baseline(bundle, rows):
    m = bundle["metrics"]
    assert m["auc"] is not None and 0.0 <= m["ece"] <= 1.0
    baseline = type_only_baseline(rows)
    assert m["auc"] >= baseline["auc"] and m["brier"] <= baseline["brier"]


def test_learned_verifier_flags_cordon_residue_the_envelope_passes(bundle, incidents):
    verifier = LearnedVerifier(bundle=bundle)
    cordon = ProposedAction(
        action_type="cordon_node",
        target="node-17",
        params={"node_name": "node-17"},
        rationale="r",
        predicted_effect="e",
    )
    verdict = verifier.verify(incidents["bad-rollout-latency"], cordon)
    assert verdict.decision == "block" and verdict.risk_score >= 0.5 and verdict.verifier == "learned"
    assert verdict.reasons[0].startswith("P(destructive)") and "held out" in verdict.reasons[0]
    policy = build_policy("learned", threshold=0.5, learned=verifier)
    combined = policy.verify(incidents["bad-rollout-latency"], cordon)
    assert combined.layers[0].decision == "allow" and combined.decision == "block"


def test_learned_verifier_allows_correct_action(bundle, incidents):
    entry = next(
        e for e in OfflineEnvAdapter().labeled_actions("itbench-sre-scenario-17") if e["label"] == "correct"
    )
    action = ProposedAction(
        action_type=entry["action_type"],
        target=entry["target"],
        params=entry["params"],
        rationale="r",
        predicted_effect="e",
    )
    assert (
        LearnedVerifier(bundle=bundle).verify(incidents["itbench-sre-scenario-17"], action).decision
        == "allow"
    )


def test_missing_model_file_has_actionable_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="make train"):
        LearnedVerifier(model_path=tmp_path / "nope.joblib")


def test_ece():
    y = np.array([0, 0, 1, 1])
    assert expected_calibration_error(y, np.array([0.0, 0.0, 1.0, 1.0])) == 0.0
    assert expected_calibration_error(y, np.array([1.0, 1.0, 0.0, 0.0])) == 1.0
