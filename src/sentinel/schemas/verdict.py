"""Verifier output contract. This is the project's contribution's central artifact — see
ARCHITECTURE_BLUEPRINT.md §6 and src/sentinel/verifier/.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Verdict(BaseModel):
    """A verifier's ruling on one ProposedAction."""

    decision: Literal["allow", "block", "revise"]
    risk_score: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(
        default_factory=list,
        description="One reason per entry, human-readable — these render directly in the triage "
        "console (Phase P5). See CLAUDE.md style rules.",
    )
    verifier: Literal["envelope", "llm_judge", "learned", "combined"]
