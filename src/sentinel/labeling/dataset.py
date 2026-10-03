"""Builds the learned verifier's labeled dataset from the fixture oracles (blueprint §6.1, §6.2).

Each fixture's `oracle.labeled_actions` becomes LabeledAction rows. The proposal text attached to each
row uses the SAME label-independent template the simulated agent emits (agent/simulated.py), so the
model can't learn the label from wording that only exists at training time.
"""

from __future__ import annotations

from collections import Counter

from sentinel.agent.simulated import _to_action
from sentinel.env.offline_adapter import OfflineEnvAdapter
from sentinel.labeling.schema import LabeledAction


def _provenance(entry: dict, source: str) -> str:
    if entry.get("provenance"):
        return entry["provenance"]
    return "hand_built" if source == "offline" else "converter_synthesized"


def build_dataset(
    env: OfflineEnvAdapter, incident_ids: list[str] | None = None, *, augmented: bool = True
) -> list[LabeledAction]:
    rows: list[LabeledAction] = []
    for incident_id in incident_ids or env.list_incidents():
        source = env.get_incident(incident_id).source
        for entry in env.candidate_actions(incident_id, augmented=augmented):
            rows.append(
                LabeledAction(
                    incident_id=incident_id,
                    action=_to_action(entry),
                    label=entry["label"],
                    provenance=_provenance(entry, source),
                    needs_review=bool(entry.get("needs_review", source != "offline")),
                )
            )
    return rows


def describe(rows: list[LabeledAction]) -> dict:
    return {
        "rows": len(rows),
        "incidents": len({r.incident_id for r in rows}),
        "labels": dict(Counter(r.label for r in rows)),
        "provenance": dict(Counter(r.provenance for r in rows)),
        "needs_review": sum(r.needs_review for r in rows),
    }
