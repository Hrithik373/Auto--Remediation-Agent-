"""Verifier ABC (blueprint §5). Every concrete verifier — envelope, LLM-judge, learned — implements
this single method and returns a Verdict. policy.py (Phase P2) combines them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sentinel.schemas.action import ProposedAction
from sentinel.schemas.incident import IncidentContext
from sentinel.schemas.verdict import Verdict


class Verifier(ABC):
    @abstractmethod
    def verify(self, incident: IncidentContext, action: ProposedAction) -> Verdict:
        raise NotImplementedError
