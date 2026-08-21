"""Reversibility helpers where the env adapter supports them — Phase P1/P2.

Only meaningful for `reversible: true` action types in config/action_envelope.yaml.
"""

from __future__ import annotations

from sentinel.env.base import EnvAdapter
from sentinel.schemas.action import ExecutionResult, ProposedAction


def rollback(env: EnvAdapter, action: ProposedAction, result: ExecutionResult) -> ExecutionResult:
    raise NotImplementedError(
        "executor.rollback.rollback is Phase P1/P2 work. See ARCHITECTURE_BLUEPRINT.md §3."
    )
