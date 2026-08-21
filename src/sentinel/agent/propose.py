"""Emits a structured, schema-valid ProposedAction from the diagnosis agent's final reasoning step —
Phase P1. Kept separate from react.py so the emission/parsing contract is independently testable.
"""

from __future__ import annotations

from sentinel.schemas.action import ProposedAction


def parse_proposed_action(raw_model_output: str) -> ProposedAction:
    raise NotImplementedError(
        "agent.propose.parse_proposed_action is Phase P1 work. See ARCHITECTURE_BLUEPRINT.md §3, §8."
    )
