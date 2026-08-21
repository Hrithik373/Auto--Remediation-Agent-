"""EnvelopeVerifier: the deterministic hard gate (blueprint §5, §6.1).

Rejects any ProposedAction whose action_type isn't in config/action_envelope.yaml's allow-list, or
whose params fail schema/least-privilege checks (blast-radius cap, forbidden namespaces). Never calls
an LLM and never depends on one — this is what makes it a "hard gate" per CLAUDE.md's golden rules.

`policy.py` (Phase P2) combines this with llm_judge.py / learned.py as:
    final = envelope_pass AND (score < threshold tau)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from sentinel.schemas.action import ProposedAction
from sentinel.schemas.incident import IncidentContext
from sentinel.schemas.verdict import Verdict
from sentinel.verifier.base import Verifier

_DEFAULT_ENVELOPE_PATH = Path(__file__).resolve().parents[3] / "config" / "action_envelope.yaml"

# Approximate risk assigned to an *allowed* action, purely as a function of its declared blast
# radius. This is not the learned/LLM risk score (Phases P2/P3) -- it just gives policy.py's
# threshold sweep (blueprint §7) something numeric to combine with for the envelope-only baseline.
_BLAST_RADIUS_RISK = {"low": 0.1, "medium": 0.35, "high": 0.7}

_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
}


class EnvelopeVerifier(Verifier):
    def __init__(self, envelope_path: str | Path = _DEFAULT_ENVELOPE_PATH) -> None:
        self._envelope_path = Path(envelope_path)
        with self._envelope_path.open(encoding="utf-8") as f:
            config = yaml.safe_load(f)
        self._allowed_actions: dict[str, dict] = config.get("allowed_actions", {})
        policy = config.get("policy", {})
        self._blast_radius_order: list[str] = policy.get("blast_radius_order", ["low", "medium", "high"])
        self._max_blast_radius: str = policy.get("max_allowed_blast_radius", "low")
        self._forbidden_namespaces: set[str] = set(policy.get("forbidden_namespaces", []))

    def _blast_radius_rank(self, level: str) -> int:
        try:
            return self._blast_radius_order.index(level)
        except ValueError:
            return len(self._blast_radius_order)  # unknown level -> treat as maximally risky

    def _block(self, reasons: list[str]) -> Verdict:
        return Verdict(decision="block", risk_score=1.0, reasons=reasons, verifier="envelope")

    def _validate_params(self, spec: dict[str, dict], params: dict[str, Any]) -> list[str]:
        """Returns a list of human-readable violations; empty list means params are valid."""
        violations: list[str] = []
        for name, rule in spec.items():
            required = rule.get("required", False)
            if name not in params:
                if required:
                    violations.append(f"missing required param '{name}'")
                continue

            value = params[name]
            expected_type = _TYPE_MAP.get(rule.get("type", "string"), str)
            # bool is a subclass of int in Python; guard against a bool sneaking past an integer check.
            if expected_type is int and isinstance(value, bool):
                violations.append(f"param '{name}' must be {rule.get('type')}, got boolean")
                continue
            if not isinstance(value, expected_type):
                violations.append(f"param '{name}' must be {rule.get('type')}, got {type(value).__name__}")
                continue

            if "min" in rule and value < rule["min"]:
                violations.append(f"param '{name}'={value} is below minimum {rule['min']}")
            if "max" in rule and value > rule["max"]:
                violations.append(f"param '{name}'={value} exceeds maximum {rule['max']}")

        # Reject unknown params too -- least-privilege: nothing sneaks through the schema.
        unknown = set(params) - set(spec)
        if unknown:
            violations.append(f"unrecognized params: {sorted(unknown)}")

        return violations

    def verify(self, incident: IncidentContext, action: ProposedAction) -> Verdict:
        del incident  # the deterministic gate only inspects the action itself

        action_spec = self._allowed_actions.get(action.action_type)
        if action_spec is None:
            return self._block(
                [f"action_type '{action.action_type}' is not in the allow-list ({self._envelope_path.name})"]
            )

        param_violations = self._validate_params(action_spec.get("params", {}), action.params)
        if param_violations:
            return self._block(param_violations)

        namespace = action.params.get("namespace")
        if namespace is not None and namespace in self._forbidden_namespaces:
            return self._block([f"namespace '{namespace}' is forbidden by policy"])

        blast_radius = action_spec.get("blast_radius", "high")
        if self._blast_radius_rank(blast_radius) > self._blast_radius_rank(self._max_blast_radius):
            return self._block(
                [
                    f"action_type '{action.action_type}' has blast_radius='{blast_radius}', "
                    f"exceeding policy cap '{self._max_blast_radius}'"
                ]
            )

        risk_score = _BLAST_RADIUS_RISK.get(blast_radius, 0.5)
        return Verdict(
            decision="allow",
            risk_score=risk_score,
            reasons=[
                f"action_type '{action.action_type}' is allow-listed",
                "params satisfy schema",
                f"blast_radius='{blast_radius}' within policy cap '{self._max_blast_radius}'",
            ],
            verifier="envelope",
        )
