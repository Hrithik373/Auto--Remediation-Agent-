# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Lists the entities of one incident (services, pods, nodes, namespaces, flags, ...) so the console's
# scenario form can offer dropdowns instead of free text. Values only -- never the oracle's labels.
"""Incident entities for the scenario form (ASSISTANT_BLUEPRINT.md §4).

Two sources, merged:
  * observable telemetry -- topology services and groups, alert targets, pod names in logs/alerts,
    namespaces named in alert descriptions;
  * the parameter VALUES of the incident's candidate actions (fixture + rule-augmented), because some
    entities (node names, flag names, revisions) never appear in telemetry. Only the values are used:
    which candidate is correct or destructive is never exposed, so the form gives no answers away.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from sentinel.env.offline_adapter import OfflineEnvAdapter
from sentinel.schemas.assistant import IncidentEntities

_NAMESPACE_IN_TEXT = re.compile(r"\bnamespace\s+([a-z0-9][\w-]*)")
# Typical generic choices for params whose values the incident doesn't name.
_DEFAULTS: dict[str, list] = {
    "replicas": [0, 1, 2, 3, 5],
    "cpu_limit": ["500m", "1", "2"],
    "memory_limit": ["512Mi", "1Gi", "2Gi"],
    "memory_quota": ["8Gi", "16Gi", "32Gi"],
    "cpu_quota": ["4", "8", "16"],
}
_TARGET_PARAMS = ("service", "deployment", "pod_name", "node_name", "configmap")


def _pods(text: str, services: list[str]) -> set[str]:
    """Pod-like names: a known service name plus generated suffixes that contain a digit (so
    'notification-service-config' is not mistaken for a pod)."""
    found = set()
    suffix = r"(?=[a-z]*\d)[a-z0-9]{4,10}"
    for svc in services:
        for m in re.finditer(rf"\b{re.escape(svc)}-{suffix}(?:-{suffix})?\b", text):
            found.add(m.group(0))
    return found


def _add(bucket: dict[str, list], name: str, value) -> None:
    if value in (None, "") or value in bucket.setdefault(name, []):
        return
    bucket[name].append(value)


def _natural(value) -> tuple:
    """Booleans first, then numbers by value, then strings with digit runs compared as numbers."""
    if isinstance(value, bool):
        return (0, int(value), ())
    if isinstance(value, int | float):
        return (1, value, ())
    parts = tuple((0, int(x), "") if x.isdigit() else (1, 0, x) for x in re.split(r"(\d+)", str(value)) if x)
    return (2, 0, parts)


def _ordered(values: list) -> list:
    return sorted(values, key=_natural)


def incident_entities(env: OfflineEnvAdapter, envelope_path: Path, incident_id: str) -> IncidentEntities:
    incident = env.get_incident(incident_id)
    t = incident.telemetry
    with envelope_path.open(encoding="utf-8") as f:
        allowed = yaml.safe_load(f)["allowed_actions"]

    services = [s for s in t.topology.get("services", []) if isinstance(s, str)]
    alert_targets = [a["target"] for a in t.alerts if a.get("target")]
    text = "\n".join([*t.logs, *(str(a) for a in t.alerts), *(str(s) for s in t.traces)])
    params: dict[str, list] = {}

    for svc in services + alert_targets:
        _add(params, "service", svc)
        _add(params, "deployment", svc)
    for pod in sorted(_pods(text, services + alert_targets)):
        _add(params, "pod_name", pod)
    for group in t.topology.get("groups", []) or []:
        if isinstance(group, dict):
            _add(params, "namespace", group.get("namespace"))
            if group.get("kind") == "ConfigMap":
                _add(params, "configmap", group.get("id"))
    for ns in _NAMESPACE_IN_TEXT.findall(text):
        _add(params, "namespace", ns)

    candidates = env.candidate_actions(incident_id)
    other_types = []
    for action in candidates:
        if action["action_type"] not in allowed and action["action_type"] not in other_types:
            other_types.append(action["action_type"])
        for name, value in action.get("params", {}).items():
            _add(params, name, value)
    for name, values in _DEFAULTS.items():
        for value in values:
            _add(params, name, value)
    for spec in allowed.values():
        for name, rule in spec.get("params", {}).items():
            if rule.get("type") == "boolean":
                _add(params, name, True)
                _add(params, name, False)

    # Alert targets first: they are what the incident is visibly about.
    targets: list[str] = []
    for name in [*alert_targets, *services, *(v for p in _TARGET_PARAMS for v in params.get(p, []))]:
        if isinstance(name, str) and name not in targets:
            targets.append(name)
    return IncidentEntities(
        incident_id=incident_id,
        targets=targets,
        params={name: _ordered(values) for name, values in sorted(params.items())},
        other_action_types=sorted(other_types),
    )
