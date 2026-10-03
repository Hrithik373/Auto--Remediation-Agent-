"""DiagnosisAgent ABC -- what the orchestrator depends on, whichever agent is configured.

The agent only PROPOSES (CLAUDE.md: "the LLM is an untrusted planner"); it never touches the
environment's control plane. Each agent owns its own UsageLedger -- never shared with a verifier.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sentinel.gateway.clients import UsageLedger
from sentinel.schemas.action import ProposedAction
from sentinel.schemas.incident import IncidentContext


class AgentExhausted(RuntimeError):
    """The agent has no further proposal for this incident (the orchestrator escalates)."""


class DiagnosisAgent(ABC):
    def __init__(self) -> None:
        self.usage = UsageLedger()

    @abstractmethod
    def propose(self, incident: IncidentContext) -> ProposedAction:
        """Fresh diagnosis -> one proposed remediation. Resets any per-incident history."""

    @abstractmethod
    def incorporate_feedback(self, incident: IncidentContext, reasons: list[str]) -> ProposedAction:
        """Closed-loop revision after a verifier 'revise' (or a non-resolving execution)."""
