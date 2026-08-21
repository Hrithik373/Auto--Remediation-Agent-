"""Verifier policy combinator — Phase P2. Not implemented yet; see PROGRESS.md.

Intended behavior (blueprint §5): final = envelope_pass AND (score < threshold tau). tau is swept in
Phase P4 to draw the risk-autonomy Pareto curve (blueprint §7). config/default.yaml's
verifier.active/threshold select which secondary verifier (llm_judge | learned) and tau to use.
"""

from __future__ import annotations

from sentinel.schemas.action import ProposedAction
from sentinel.schemas.incident import IncidentContext
from sentinel.schemas.verdict import Verdict
from sentinel.verifier.base import Verifier
from sentinel.verifier.envelope import EnvelopeVerifier


class CombinedPolicy(Verifier):
    """envelope AND (secondary_verifier.risk_score < threshold)."""

    def __init__(self, envelope: EnvelopeVerifier, secondary: Verifier | None, threshold: float) -> None:
        self._envelope = envelope
        self._secondary = secondary
        self._threshold = threshold

    def verify(self, incident: IncidentContext, action: ProposedAction) -> Verdict:
        raise NotImplementedError(
            "CombinedPolicy is Phase P2 work. See ARCHITECTURE_BLUEPRINT.md §5, §7, §8."
        )
