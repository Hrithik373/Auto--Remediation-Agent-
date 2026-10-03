"""Executor -- the ONLY path from a ProposedAction to EnvAdapter.apply_action (blueprint §5).

CLAUDE.md golden rules, enforced here in code rather than by convention:
  * auto_execute defaults to False; a real (non-dry-run) apply requires it explicitly.
  * No action reaches run(dry_run=False) without a verifier verdict: the caller must pass the Verdict
    from verifier.policy, and anything other than decision == "allow" is refused.
Dry runs need no verdict -- they never touch the environment's state.
"""

from __future__ import annotations

import logging

from sentinel.env.base import EnvAdapter
from sentinel.schemas.action import ExecutionResult, ProposedAction
from sentinel.schemas.verdict import Verdict

logger = logging.getLogger(__name__)


class ExecutionRefused(RuntimeError):
    """A real apply was requested without the required config flag or an 'allow' verdict."""


class Executor:
    def __init__(self, env: EnvAdapter, *, auto_execute: bool = False) -> None:
        self._env = env
        # Golden rule (CLAUDE.md): auto_execute defaults to False everywhere.
        self._auto_execute = auto_execute
        self.log: list[tuple[ProposedAction, ExecutionResult]] = []

    @property
    def auto_execute(self) -> bool:
        return self._auto_execute

    def _check_real_apply(self, action: ProposedAction, verdict: Verdict | None) -> None:
        if not self._auto_execute:
            raise ExecutionRefused(
                "Refusing to apply a real action: auto_execute is False. Set execution.auto_execute="
                "true in config explicitly to allow real (non-dry-run) execution."
            )
        if verdict is None or verdict.decision != "allow":
            decision = verdict.decision if verdict else "none"
            raise ExecutionRefused(
                f"Refusing to apply {action.action_type} on {action.target}: real execution requires a "
                f"verifier 'allow' verdict (got {decision})."
            )

    def run(
        self, action: ProposedAction, *, verdict: Verdict | None = None, dry_run: bool = True
    ) -> ExecutionResult:
        if not dry_run:
            self._check_real_apply(action, verdict)
        try:
            result = self._env.apply_action(action, dry_run=dry_run)
        except Exception as exc:  # env/cluster failures become a recorded result, not a crash
            logger.exception("apply_action failed for %s on %s", action.action_type, action.target)
            result = ExecutionResult(executed=False, dry_run=dry_run, error=f"{type(exc).__name__}: {exc}")
        self.log.append((action, result))
        logger.info(
            "%s %s -> %s executed=%s resolved=%s",
            "DRY-RUN" if dry_run else "APPLY",
            action.action_type,
            action.target,
            result.executed,
            result.resolved,
        )
        return result
