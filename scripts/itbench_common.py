"""Shared ITBench-Lite snapshot readers for fetch_itbench.py and convert_itbench.py.

Two ground_truth.yaml shapes exist in the v0.2 SRE snapshots (verified, not assumed): most scenarios
put `fault/alerts/groups/...` at the top level, but some (e.g. Scenario-20/23/31/105) wrap the same
keys in a Kubernetes-style `{apiVersion, kind: GroundTruth, metadata, spec: {...}}` envelope.
load_ground_truth() normalizes both to the flat shape.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml


def load_ground_truth(scenario_dir: Path) -> dict:
    with (scenario_dir / "ground_truth.yaml").open(encoding="utf-8") as f:
        gt = yaml.safe_load(f)
    if "spec" in gt and "fault" not in gt:
        gt = gt["spec"]
    for key in ("fault", "alerts", "groups", "aliases", "propagations", "recommended_actions"):
        gt[key] = gt.get(key) or []
    return gt


def filter_base_name(pattern: str) -> str:
    """'frontend-proxy-.*' / 'frontend-proxy\\b' / '^cart$' -> 'frontend-proxy' / 'cart'."""
    name = re.sub(r"\\b|\^|\$", "", pattern)
    name = re.sub(r"-?\.\*.*$", "", name)
    return name.strip("-")


def group_base_name(group: dict) -> str:
    filters = group.get("filter") or []
    if filters:
        base = filter_base_name(filters[0])
        if base:
            return base
    return re.sub(r"-\d+$", "", group["id"])


def scenario_namespaces(gt: dict) -> set[str]:
    namespaces = {g["namespace"] for g in gt["groups"] if g.get("namespace")}
    return namespaces or {"otel-demo"}


def firing_alerts(scenario_dir: Path, gt: dict) -> list[dict]:
    """Firing alerts scoped to the scenario's namespaces, as raw Prometheus alert dicts.

    Prefers the curated `alerts_in_alerting_state_*.json` snapshot; falls back to the union of the
    per-minute `alerts/alerts_at_*.json` snapshots when a scenario doesn't ship the curated file.
    """
    namespaces = scenario_namespaces(gt)
    curated = sorted(scenario_dir.rglob("alerts_in_alerting_state*.json"))
    if curated:
        with curated[0].open(encoding="utf-8") as f:
            raw = json.load(f)
        alerts = raw.get("data", {}).get("alerts", []) if isinstance(raw, dict) else raw
    else:
        alerts = []
        for path in sorted((scenario_dir / "alerts").glob("alerts_at_*.json")):
            with path.open(encoding="utf-8") as f:
                alerts.extend(json.load(f))

    seen: set[tuple] = set()
    scoped = []
    for alert in alerts:
        labels = alert.get("labels", {})
        if alert.get("state", "firing") != "firing" or labels.get("namespace") not in namespaces:
            continue
        key = (labels.get("alertname"), alert_target(alert))
        if key not in seen:
            seen.add(key)
            scoped.append(alert)
    return scoped


def alert_target(alert: dict) -> str:
    labels = alert.get("labels", {})
    for key in ("service_name", "service", "deployment", "pod", "node", "namespace"):
        if labels.get(key):
            return labels[key]
    return labels.get("alertname", "unknown")


def alerted_services(scenario_dir: Path, gt: dict) -> set[str]:
    """Service names that alerted: from firing alerts' labels plus ground-truth alert groups."""
    services = {
        a["labels"]["service_name"]
        for a in firing_alerts(scenario_dir, gt)
        if a["labels"].get("service_name")
    }
    groups = {g["id"]: g for g in gt["groups"]}
    for alert in gt["alerts"]:
        group = groups.get(alert.get("group_id"))
        if group and group.get("kind") in ("Service", "Pod", "Deployment"):
            services.add(group_base_name(group))
    return services
