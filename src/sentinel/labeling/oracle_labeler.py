"""Derives ActionLabels from (a) the env oracle, (b) a fault-family -> acceptable-action-family rules
table, (c) blast-radius heuristics on params. Phase P3 — see PROGRESS.md, blueprint §6.1.

For the offline fixtures, labels are currently hand-authored directly in
fixtures/incidents/*.json (`oracle.labeled_actions[].label`) rather than derived by this module --
Phase P3 replaces that manual step with this pipeline and extends it to agent-proposed actions that
don't exactly match a fixture entry.
"""

from __future__ import annotations

from sentinel.env.base import EnvAdapter
from sentinel.labeling.schema import ActionLabel
from sentinel.schemas.action import ProposedAction


def derive_label(env: EnvAdapter, action: ProposedAction, incident_id: str) -> ActionLabel:
    raise NotImplementedError(
        "labeling.oracle_labeler.derive_label is Phase P3 work. See ARCHITECTURE_BLUEPRINT.md §6.1."
    )
