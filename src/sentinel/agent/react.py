"""ReAct diagnosis loop — Phase P1. Not implemented yet; see PROGRESS.md.

Per CLAUDE.md: "Don't add a heavy agent framework; keep the ReAct loop in-repo and readable." Calls
agent/tools.py over the current IncidentContext and terminates by calling propose.py to emit a
ProposedAction. The agent only proposes — it never calls EnvAdapter.apply_action itself.
"""

from __future__ import annotations

from sentinel.schemas.action import ProposedAction
from sentinel.schemas.incident import IncidentContext


class DiagnosisAgent:
    def __init__(self, *, model: str = "claude-sonnet-5", max_tool_calls: int = 10) -> None:
        self._model = model
        self._max_tool_calls = max_tool_calls

    def propose(self, incident: IncidentContext) -> ProposedAction:
        raise NotImplementedError(
            "agent.react.DiagnosisAgent.propose is Phase P1 work. See ARCHITECTURE_BLUEPRINT.md §3, §8."
        )

    def incorporate_feedback(self, incident: IncidentContext, reasons: list[str]) -> ProposedAction:
        """Closed-loop revision after a verifier "revise" decision (blueprint §5, orchestrator loop)."""
        raise NotImplementedError(
            "agent.react.DiagnosisAgent.incorporate_feedback is Phase P1/P2 work. "
            "See ARCHITECTURE_BLUEPRINT.md §5."
        )
