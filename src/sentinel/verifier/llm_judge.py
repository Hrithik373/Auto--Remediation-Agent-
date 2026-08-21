"""LLM-judge verifier (v1) — Phase P2. Not implemented yet; see PROGRESS.md.

Intended behavior (blueprint §5): prompt a model with (compacted incident + proposed action +
predicted effect) and ask for a structured {allow|block|revise} + risk_score + reasons JSON verdict.
Must stay independent of the diagnosis agent's prompt/state (CLAUDE.md: "Don't let the diagnosis
agent and the verifier share state or prompts").
"""

from __future__ import annotations

from sentinel.schemas.action import ProposedAction
from sentinel.schemas.incident import IncidentContext
from sentinel.schemas.verdict import Verdict
from sentinel.verifier.base import Verifier


class LLMJudgeVerifier(Verifier):
    def __init__(self, *, model: str = "claude-sonnet-5") -> None:
        self._model = model

    def verify(self, incident: IncidentContext, action: ProposedAction) -> Verdict:
        raise NotImplementedError("LLMJudgeVerifier is Phase P2 work. See ARCHITECTURE_BLUEPRINT.md §5, §8.")
