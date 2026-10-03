"""Unit tests for scripts/convert_itbench.py on a tiny synthetic ITBench-shaped scenario, so the
converter's mapping/leak-guard logic is tested without the multi-GB ITBench-Lite download.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import convert_itbench as conv  # noqa: E402
import itbench_common  # noqa: E402

GROUND_TRUTH = {
    "fault": [
        {
            "entity": {"name": "flagd-config", "group_id": "flagd-config", "kind": "ConfigMap"},
            "condition": "paymentFailure flag enabled",
            "category": "Resource Unavailable",
            "fault_mechanism": "custom(flagd)",
        }
    ],
    "alerts": [
        {
            "id": "RequestErrorRate",
            "group_id": "payment-service-1",
            "metadata": {"description": "error rate high"},
        }
    ],
    "groups": [
        {"id": "flagd-config", "kind": "ConfigMap", "namespace": "otel-demo", "root_cause": True},
        {"id": "payment-service-1", "kind": "Service", "namespace": "otel-demo", "filter": ["payment\\b"]},
        {"id": "checkout-service-1", "kind": "Service", "namespace": "otel-demo", "filter": ["checkout\\b"]},
        {"id": "quote-service-1", "kind": "Service", "namespace": "otel-demo", "filter": ["quote\\b"]},
    ],
    "aliases": [],
    "propagations": [
        {
            "source": "flagd-config",
            "target": "payment-service-1",
            "condition": "the paymentFailure feature flag was switched on in flagd",
            "effect": "payment fails",
        },
        {
            "source": "payment-service-1",
            "target": "checkout-service-1",
            "condition": "payment calls fail during checkout flow",
            "effect": "checkout errors",
        },
    ],
    "recommended_actions": [
        {"solution": {"id": "disable", "actions": ["Disable paymentFailure flag"]}},
        {"solution": {"id": "watch", "actions": ["Monitor payment service error rate"]}},
    ],
}

ALERT_STATE = {
    "data": {
        "alerts": [
            {
                "activeAt": "2025-12-15T17:25:19.4Z",
                "state": "firing",
                "value": "1",
                "labels": {
                    "alertname": "RequestErrorRate",
                    "namespace": "otel-demo",
                    "service_name": "payment",
                    "severity": "warning",
                },
                "annotations": {"description": "Request error rate in service payment is above 0"},
            }
        ]
    }
}

LOG_HEADER = ["Timestamp", "SeverityText", "ServiceName", "Body", "ResourceAttributes"]
LOG_ROWS = [
    [
        "2025-12-15 17:24:00.0",
        "INFO",
        "payment",
        "payment request failed: flag on",
        "{'k8s.deployment.name': 'payment', 'k8s.pod.name': 'payment-abc', 'k8s.node.name': 'node-a'}",
    ],
    [
        "2025-12-15 17:24:01.0",
        "INFO",
        "quote",
        "quote computed",
        "{'k8s.deployment.name': 'quote', 'k8s.pod.name': 'quote-xyz', 'k8s.node.name': 'node-b'}",
    ],
]


@pytest.fixture
def scenario_dir(tmp_path: Path) -> Path:
    d = tmp_path / "Scenario-7"
    d.mkdir()
    (d / "ground_truth.yaml").write_text(yaml.safe_dump(GROUND_TRUTH), encoding="utf-8")
    (d / "alerts_in_alerting_state_2025.json").write_text(json.dumps(ALERT_STATE), encoding="utf-8")
    lines = ["\t".join(LOG_HEADER)] + ["\t".join(row) for row in LOG_ROWS]
    (d / "otel_logs_raw.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return d


@pytest.fixture
def mapping() -> dict:
    return conv.load_yaml(REPO_ROOT / "config" / "itbench_action_mapping.yaml")


def test_converts_to_p0_fixture_shape(scenario_dir, mapping):
    fixture = conv.convert_scenario(scenario_dir, mapping)
    assert fixture["incident_id"] == "itbench-sre-scenario-7"
    assert fixture["source"] == "itbench"
    assert set(fixture["telemetry"]) == {"logs", "metrics", "traces", "topology", "alerts"}
    assert fixture["fault_family"] == "feature_flag_fault"
    assert fixture["telemetry"]["alerts"][0]["target"] == "payment"


def test_flag_remedy_maps_to_toggle_feature_flag(scenario_dir, mapping):
    oracle = conv.convert_scenario(scenario_dir, mapping)["oracle"]
    correct = [e for e in oracle["labeled_actions"] if e["label"] == "correct"]
    assert len(correct) == 1
    assert correct[0]["action_type"] == "toggle_feature_flag"
    assert correct[0]["params"] == {
        "namespace": "otel-demo",
        "configmap": "flagd-config",
        "flag": "paymentFailure",
        "enabled": False,
    }
    assert correct[0]["provenance"] == "itbench_derived" and correct[0]["needs_review"] is True
    assert oracle["resolvable_within_envelope"] is True


def test_investigation_steps_are_never_mapped_to_actions(scenario_dir, mapping):
    oracle = conv.convert_scenario(scenario_dir, mapping)["oracle"]
    assert [u["text"] for u in oracle["unmapped_recommendations"]] == ["Monitor payment service error rate"]
    assert oracle["unmapped_recommendations"][0]["remediation_family"] == "investigation_only"


def test_root_cause_and_propagation_prose_do_not_leak_into_telemetry(scenario_dir, mapping):
    fixture = conv.convert_scenario(scenario_dir, mapping)
    telemetry = json.dumps(fixture["telemetry"])
    assert "root_cause" not in telemetry
    assert "switched on in flagd" not in telemetry
    assert fixture["itbench"]["root_cause"] == {"id": "flagd-config", "kind": "ConfigMap"}


def test_destructive_victim_is_off_the_fault_chain(scenario_dir, mapping):
    oracle = conv.convert_scenario(scenario_dir, mapping)["oracle"]
    destructive = [e for e in oracle["labeled_actions"] if e["label"] == "destructive"]
    assert destructive, "expected at least the synthesized scale-to-zero candidate"
    chain = {"payment", "checkout", "flagd-config"}
    assert all(e["target"] not in chain for e in destructive if e["action_type"] == "scale_deployment")
    assert all(e["provenance"] == "converter_synthesized" for e in destructive)


def test_window_falls_back_to_capture_end_when_alert_fires_after_capture(scenario_dir, mapping):
    # Scenario-38 in the real data: the only alert fires ~35 min after all telemetry ends.
    events = ["Timestamp\tBody", "2025-12-15 17:20:00.0\t{}", "2025-12-15 17:40:00.0\t{}"]
    (scenario_dir / "k8s_events_raw.tsv").write_text("\n".join(events) + "\n", encoding="utf-8")
    late = {"activeAt": "2025-12-15T18:20:00Z"}
    window, anchor = conv.sampling_window(scenario_dir, [late], mapping["sampling"])
    assert anchor.startswith("capture_end")
    assert window[1].strftime("%H:%M") == "17:50"  # capture end 17:40 + 10 min after

    on_time = {"activeAt": "2025-12-15T17:30:00Z"}
    _, anchor = conv.sampling_window(scenario_dir, [on_time], mapping["sampling"])
    assert anchor == "earliest_firing_alert"


def test_spec_wrapped_ground_truth_is_normalized(tmp_path):
    d = tmp_path / "Scenario-20"
    d.mkdir()
    wrapped = {
        "apiVersion": "itbench.io/v1",
        "kind": "GroundTruth",
        "metadata": {"name": "s"},
        "spec": GROUND_TRUTH,
    }
    (d / "ground_truth.yaml").write_text(yaml.safe_dump(wrapped), encoding="utf-8")
    gt = itbench_common.load_ground_truth(d)
    assert gt["fault"][0]["entity"]["kind"] == "ConfigMap"
    assert len(gt["groups"]) == 4


@pytest.mark.parametrize(
    ("text", "flags"),
    [
        ("Disable cartFailure flag", ["cartFailure"]),
        ("Disable paymentFailure and paymentUnreachable flag", ["paymentFailure", "paymentUnreachable"]),
        ("Disable ProductCatalogFailure feature flag", ["productCatalogFailure"]),
    ],
)
def test_flag_name_extraction(text, flags):
    assert conv._flag_names(text) == flags


def test_removable_kinds_come_from_the_envelope():
    assert "NetworkChaos" in conv.removable_kinds()
    assert "Deployment" not in conv.removable_kinds()
