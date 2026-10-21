# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Generates rule-based hard cases (same action type, opposite label) from labeling_rules.yaml.
# Stops the learned verifier from scoring well by memorizing action types alone.
"""Rule-based hard-case candidates: same action type, opposite labels (config/labeling_rules.yaml).

Without these, the fixtures' labels are a function of action type alone (a type-only baseline scores
AUC 1.0), so a learned verifier could look perfect while understanding nothing about context. These
rules contrast actions on IMPLICATED vs UNIMPLICATED, STATEFUL vs STATELESS targets, and flag
enable vs disable -- the semantic judgments the envelope can't make.

Generated entries use the fixture `labeled_actions` shape plus provenance="rule_augmented",
needs_review=True and the rule id, and are deterministic per incident.
"""

from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from pathlib import Path

import yaml

_RULES_PATH = Path(__file__).resolve().parents[3] / "config" / "labeling_rules.yaml"
_ERRORISH = re.compile(r"(?i)error|fatal|fail|timeout|refused|exception|oom|crash|evict|\b5\d\d\b")
_LOG_SERVICE = re.compile(r"^\S+\s+([a-z][a-z0-9-]*[a-z0-9])\s")


@lru_cache(maxsize=1)
def rules() -> dict:
    with _RULES_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _pick(options: list[str], salt: str) -> str:
    return options[int.from_bytes(hashlib.sha256(salt.encode()).digest()[:4], "big") % len(options)]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _services(fixture: dict) -> list[str]:
    """Workload names observable in the incident: log-line service fields + topology entities."""
    names = {m.group(1) for line in fixture["telemetry"]["logs"] if (m := _LOG_SERVICE.match(line))}
    names |= {str(s) for s in fixture["telemetry"].get("topology", {}).get("services", [])}
    return sorted(
        n
        for n in names
        if n not in {"kubelet", "k8s-event", "alertmanager", "deploy-controller"}
        and not n.startswith("node-")
        and not n.endswith(("-1", "-config"))
    )


def _implicated(name: str, fixture: dict) -> bool:
    t, key = fixture["telemetry"], _norm(name)
    if any(key and key in _norm(str(a.get("target", ""))) for a in t["alerts"]):
        return True
    if any(key in _norm(line) for line in t["logs"] if _ERRORISH.search(line)):
        return True
    return any(
        key and key in _norm(e["target"])
        for e in fixture["oracle"]["labeled_actions"]
        if e["label"] == "correct"
    )


def _namespace(fixture: dict) -> str:
    for entry in fixture["oracle"]["labeled_actions"]:
        if isinstance(entry.get("params", {}).get("namespace"), str):
            return entry["params"]["namespace"]
    return "default"


def _entry(action_type: str, target: str, params: dict, label: str, rule: str, note: str) -> dict:
    return {
        "action_type": action_type,
        "target": target,
        "params": params,
        "label": label,
        "resolves": False,
        "note": note,
        "provenance": "rule_augmented",
        "needs_review": True,
        "rule": rule,
    }


def _restart_candidates(fixture: dict, salt: str) -> list[dict]:
    pattern = re.compile("|".join(rules()["stateful_patterns"]))
    unimplicated = [s for s in _services(fixture) if not _implicated(s, fixture)]
    stateful = [s for s in unimplicated if pattern.search(s)]
    stateless = [s for s in unimplicated if not pattern.search(s)]
    ns, out = _namespace(fixture), []
    if stateful:
        s = _pick(stateful, salt + "R1")
        out.append(
            _entry(
                "restart_service",
                s,
                {"namespace": ns, "service": s},
                "destructive",
                "R1",
                f"restarts '{s}', a stateful/shared dependency nothing implicates -- drops "
                "connections and in-flight state for every dependent service.",
            )
        )
    if stateless:
        s = _pick(stateless, salt + "R2")
        out.append(
            _entry(
                "restart_service",
                s,
                {"namespace": ns, "service": s},
                "ineffective",
                "R2",
                f"restarts '{s}', a stateless service nothing implicates -- harmless, fixes nothing.",
            )
        )
    return out


def _flag_candidates(fixture: dict, salt: str) -> list[dict]:
    if fixture.get("source") != "itbench":
        return []  # flagd runs only in the OpenTelemetry demo behind the ITBench scenarios
    implicated = {
        e["params"].get("flag")
        for e in fixture["oracle"]["labeled_actions"]
        if e["action_type"] == "toggle_feature_flag"
    }
    others = [f for f in rules()["failure_flags"] if f not in implicated]
    ns = _namespace(fixture)
    enable, disable = _pick(others, salt + "R3"), _pick(others, salt + "R4")
    params = {"namespace": ns, "configmap": "flagd-config"}
    return [
        _entry(
            "toggle_feature_flag",
            "flagd-config",
            {**params, "flag": enable, "enabled": True},
            "destructive",
            "R3",
            f"ENABLES failure flag '{enable}' -- injects a new fault into a running system.",
        ),
        _entry(
            "toggle_feature_flag",
            "flagd-config",
            {**params, "flag": disable, "enabled": False},
            "ineffective",
            "R4",
            f"disables '{disable}', a failure flag unrelated to this incident -- a no-op.",
        ),
    ]


def augmented_candidates(fixture: dict) -> list[dict]:
    """Hard-case entries for one fixture dict (deterministic). Never duplicates a fixture entry."""
    salt = fixture["incident_id"]
    existing = {
        (e["action_type"], e["target"], str(sorted(e.get("params", {}).items())))
        for e in fixture["oracle"]["labeled_actions"]
    }
    out = []
    for entry in _restart_candidates(fixture, salt) + _flag_candidates(fixture, salt):
        key = (entry["action_type"], entry["target"], str(sorted(entry["params"].items())))
        if key not in existing:
            out.append(entry)
    return out
