# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Verdict and LayerVerdict: the verifier's decision, risk score and reasons per layer.
# The console's VerdictCard renders every layer from this model.
"""Verifier output contract. This is the project's contribution's central artifact — see
ARCHITECTURE_BLUEPRINT.md §6 and src/sentinel/verifier/.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LayerVerdict(BaseModel):
    """One verification layer's sub-ruling within a combined Verdict.

    Added for FRONTEND_BLUEPRINT.md §6.1's VerdictCard, which must render the decision pipeline
    ("envelope passed, judge blocked, why") rather than a single collapsed decision — the layered
    view is the project's contribution and CLAUDE.md's frontend addendum requires it stay visible.
    `verifier/policy.py`'s CombinedPolicy (Phase P2) populates `Verdict.layers` with one entry per
    active layer; a single-layer verdict (e.g. EnvelopeVerifier alone) leaves `layers` empty.
    """

    verifier: Literal["envelope", "llm_judge", "learned"]
    decision: Literal["allow", "block", "revise", "skipped"] = Field(
        description="'skipped' means this layer wasn't active for the run's verifier config -- the "
        "console grays it out rather than omitting it (blueprint §6.1: 'the viewer should see which "
        "layers were in play')."
    )
    risk_score: float | None = Field(default=None, ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


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
    layers: list[LayerVerdict] = Field(
        default_factory=list,
        description="Per-layer breakdown when verifier='combined' (Phase P2 policy.py). Empty for a "
        "single-layer verdict (e.g. envelope alone in Phase P0/P1).",
    )
