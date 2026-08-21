#!/usr/bin/env python
"""`make offline` entry point — the P0 acceptance check from ARCHITECTURE_BLUEPRINT.md §8:

    "make offline loads an incident and prints its context; tests pass; zero cluster required."

Loads one fixture through OfflineEnvAdapter, prints its IncidentContext, then runs the deterministic
EnvelopeVerifier against that fixture's labeled `correct` and `destructive` example actions to show
the P0 slice of the pipeline (env adapter -> schemas -> envelope gate) working end to end.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sentinel.env.offline_adapter import OfflineEnvAdapter  # noqa: E402
from sentinel.schemas.action import ProposedAction  # noqa: E402
from sentinel.verifier.envelope import EnvelopeVerifier  # noqa: E402

INCIDENT_ID = "pod-crashloop"


def main() -> None:
    env = OfflineEnvAdapter()
    print(f"Offline fixtures available: {env.list_incidents()}\n")

    incident = env.get_incident(INCIDENT_ID)
    print(f"=== IncidentContext: {incident.incident_id} ===")
    print(f"source:        {incident.source}")
    print(f"fault_family:  {incident.fault_family}")
    print(f"budget_tokens: {incident.budget_tokens}")
    print(f"alerts:        {incident.telemetry.alerts}")
    print(f"log lines:     {len(incident.telemetry.logs)}")
    print(f"metrics:       {list(incident.telemetry.metrics)}")
    print(f"topology:      {json.dumps(incident.telemetry.topology)}\n")

    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "incidents" / f"{INCIDENT_ID}.json"
    labeled_actions = json.loads(fixture_path.read_text(encoding="utf-8"))["oracle"]["labeled_actions"]
    correct_entry = next(a for a in labeled_actions if a["label"] == "correct")
    destructive_entry = next(a for a in labeled_actions if a["label"] == "destructive")

    verifier = EnvelopeVerifier()
    for label, entry in (("correct", correct_entry), ("destructive", destructive_entry)):
        action = ProposedAction(
            action_type=entry["action_type"],
            target=entry["target"],
            params=entry["params"],
            rationale=f"fixture-labeled '{label}' action",
            predicted_effect=entry.get("note", ""),
        )
        verdict = verifier.verify(incident, action)
        print(f"=== EnvelopeVerifier.verify() on the '{label}'-labeled action ===")
        print(f"action:   {action.action_type} -> {action.target} {action.params}")
        print(f"decision: {verdict.decision}  (risk_score={verdict.risk_score})")
        for reason in verdict.reasons:
            print(f"  - {reason}")
        print()


if __name__ == "__main__":
    main()
