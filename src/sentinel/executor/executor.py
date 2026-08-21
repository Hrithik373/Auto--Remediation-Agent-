"""Executor — Phase P1. Not implemented yet; see PROGRESS.md.

Wraps EnvAdapter.apply_action(). The orchestrator (Phase P2) must only call Executor.run(...) after a
verifier "allow" decision -- see the golden rules in CLAUDE.md.
"""

from __future__ import annotations

from sentinel.env.base import EnvAdapter
from sentinel.schemas.action import ExecutionResult, ProposedAction


class Executor:
    def __init__(self, env: EnvAdapter, *, auto_execute: bool = False) -> None:
        self._env = env
        # Golden rule (CLAUDE.md): auto_execute defaults to False everywhere.
        self._auto_execute = auto_execute

    def run(self, action: ProposedAction, *, dry_run: bool = True) -> ExecutionResult:
        if not dry_run and not self._auto_execute:
            raise RuntimeError(
                "Refusing to apply a real action: auto_execute is False. Set execution.auto_execute="
                "true in config explicitly to allow real (non-dry-run) execution."
            )
        raise NotImplementedError(
            "executor.executor.Executor.run is Phase P1 work. See ARCHITECTURE_BLUEPRINT.md §3, §8."
        )
