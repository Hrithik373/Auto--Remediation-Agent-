"""OfflineEnvAdapter: reads hand-built snapshot fixtures from disk. No cluster, no network.

This is the de-risking decision from ARCHITECTURE_BLUEPRINT.md §5: implemented first and fully so the
whole pipeline is runnable and testable with zero Kubernetes. AIOpsLab/ITBench adapters implement the
same EnvAdapter ABC and are additive.

Fixture format (fixtures/incidents/<incident_id>.json):
    {
      "incident_id", "source", "fault_family", "budget_tokens", "telemetry": {...},
      "oracle": {
        "acceptable_action_families": [...],
        "labeled_actions": [
          {"action_type", "target", "params", "label", "resolves", "note"}, ...
        ]
      }
    }

`label` follows the blueprint §6.1 taxonomy: correct | ineffective | destructive | out_of_envelope.
"""

from __future__ import annotations

import json
from pathlib import Path

from sentinel.env.base import EnvAdapter
from sentinel.schemas.action import ExecutionResult, ProposedAction
from sentinel.schemas.incident import IncidentContext, Telemetry

_DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "incidents"

# labeled_actions labels that indicate the action is NOT destructive, i.e. safe to execute
# (blueprint §6.1: destructive is the class the verifier must catch).
_SAFE_LABELS = {"correct", "ineffective"}
_UNSAFE_LABELS = {"destructive"}

# Identifiers an agent can't be expected to reproduce exactly; everything else must match.
VOLATILE_PARAMS = frozenset({"pod_name", "revision", "cache_key"})


def params_compatible(labeled: dict, proposed: dict) -> bool:
    """True when every param present in BOTH dicts agrees, ignoring VOLATILE_PARAMS.

    Previously a bare (action_type, target) match was enough, which let e.g. disabling an unrelated
    flag on flagd-config, or scaling orders-service to 0 replicas, inherit the CORRECT entry's
    `resolves: true`."""
    shared = (set(labeled) & set(proposed)) - VOLATILE_PARAMS
    return all(labeled[k] == proposed[k] for k in shared)


class OfflineEnvAdapter(EnvAdapter):
    """Cluster-free EnvAdapter backed by JSON fixtures on disk."""

    def __init__(self, fixtures_dir: str | Path = _DEFAULT_FIXTURES_DIR) -> None:
        self._fixtures_dir = Path(fixtures_dir)
        self._cache: dict[str, dict] = {}
        # Tracks whether apply_action has resolved an incident (only real, non-dry-run applies count).
        self._resolved: dict[str, bool] = {}
        # EnvAdapter.apply_action() takes no incident_id (blueprint §5) -- the adapter tracks which
        # incident is "live" from the most recent get_incident() call, mirroring how a real cluster
        # adapter would hold a connection/session scoped to the incident under investigation.
        self._current_incident_id: str | None = None

    # -- loading -----------------------------------------------------------------

    def _load(self, incident_id: str) -> dict:
        if incident_id not in self._cache:
            path = self._fixtures_dir / f"{incident_id}.json"
            if not path.exists():
                raise FileNotFoundError(f"No offline fixture for incident_id={incident_id!r} at {path}")
            with path.open(encoding="utf-8") as f:
                self._cache[incident_id] = json.load(f)
        return self._cache[incident_id]

    def list_incidents(self) -> list[str]:
        if not self._fixtures_dir.exists():
            return []
        return sorted(p.stem for p in self._fixtures_dir.glob("*.json"))

    def get_incident(self, incident_id: str) -> IncidentContext:
        data = self._load(incident_id)
        self._current_incident_id = incident_id
        return IncidentContext(
            incident_id=data["incident_id"],
            source=data.get("source", "offline"),
            fault_family=data.get("fault_family"),
            telemetry=Telemetry(**data["telemetry"]),
            budget_tokens=data.get("budget_tokens", 8000),
        )

    # -- oracle lookup -------------------------------------------------------------

    def oracle(self, incident_id: str) -> dict:
        """The fixture's eval-only oracle block (a copy). Offline-adapter-specific -- deliberately not
        on the EnvAdapter ABC. Consumers: labeling/ and agent/simulated.py's stimulus generator.
        Verifiers must never be handed this."""
        return json.loads(json.dumps(self._load(incident_id).get("oracle", {})))

    def labeled_actions(self, incident_id: str) -> list[dict]:
        return self.oracle(incident_id).get("labeled_actions", [])

    def candidate_actions(self, incident_id: str, *, augmented: bool = True) -> list[dict]:
        """Fixture-labeled actions plus (by default) the rule-based hard cases from
        labeling/augment.py -- same action type, opposite labels. Eval-only, like oracle()."""
        entries = self.labeled_actions(incident_id)
        if augmented:
            from sentinel.labeling.augment import augmented_candidates

            entries += augmented_candidates(json.loads(json.dumps(self._load(incident_id))))
        return entries

    def _find_labeled_action(self, action: ProposedAction, incident_id: str) -> dict | None:
        """Match a ProposedAction to a fixture's oracle.labeled_actions entry.

        Tries an exact (action_type, target, params) match first, then a looser match that still
        requires every SHARED param to agree except volatile identifiers (see params_compatible) --
        real agent proposals won't echo a pod name or revision verbatim, but a different flag, a
        different replica count or enabled-vs-disabled is a different action.
        """
        data = self._load(incident_id)
        labeled = data.get("oracle", {}).get("labeled_actions", [])

        for entry in labeled:
            if (
                entry["action_type"] == action.action_type
                and entry["target"] == action.target
                and entry.get("params", {}) == action.params
            ):
                return entry

        for entry in labeled:
            if (
                entry["action_type"] == action.action_type
                and entry["target"] == action.target
                and params_compatible(entry.get("params", {}), action.params)
            ):
                return entry

        return None

    # -- execution -------------------------------------------------------------

    def apply_action(self, action: ProposedAction, dry_run: bool) -> ExecutionResult:
        if self._current_incident_id is None:
            raise RuntimeError(
                "OfflineEnvAdapter.apply_action() called before get_incident() -- there is no "
                "'live' incident to apply the action against."
            )
        incident_id = self._current_incident_id
        entry = self._find_labeled_action(action, incident_id)

        if entry is None:
            # Unrecognized action against this incident's fixture: simulate a no-op, non-resolving apply.
            return ExecutionResult(executed=not dry_run, dry_run=dry_run, resolved=None, side_effects=[])

        resolves = bool(entry.get("resolves", False))
        side_effects = [entry["note"]] if entry.get("note") else []

        if not dry_run:
            if resolves:
                self._resolved[incident_id] = True
            elif entry.get("label") in _UNSAFE_LABELS:
                side_effects.append(f"UNSAFE ACTION EXECUTED: label={entry.get('label')}")

        return ExecutionResult(
            executed=not dry_run,
            dry_run=dry_run,
            resolved=(resolves if not dry_run else None),
            side_effects=side_effects,
        )

    def reset(self, incident_id: str) -> None:
        self._load(incident_id)  # raises if unknown
        self._resolved.pop(incident_id, None)

    def evaluate(self, incident_id: str) -> bool:
        self._load(incident_id)  # raises if unknown
        return self._resolved.get(incident_id, False)

    def ground_truth_action_safe(self, action: ProposedAction, incident_id: str) -> bool | None:
        entry = self._find_labeled_action(action, incident_id)
        if entry is None:
            return None
        label = entry.get("label")
        if label in _SAFE_LABELS:
            return True
        if label in _UNSAFE_LABELS:
            return False
        return None  # out_of_envelope: not a safety judgment, envelope.py handles it deterministically
