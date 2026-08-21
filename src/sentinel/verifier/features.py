"""Feature extraction for LearnedVerifier — Phase P3. Not implemented yet; see PROGRESS.md.

Per blueprint §6.2:
  - Action features: action_type (one-hot), target scope, param blast-radius, reversibility flag,
    matches-fault-family (from topology reasoning).
  - Context features: fault-family signals, #anomalous services, alert severity, topology depth of
    target, TF-IDF over the agent's rationale.
  - Agent-confidence features: token-logprob confidence if available, self-reported confidence.
"""

from __future__ import annotations

from sentinel.schemas.action import ProposedAction
from sentinel.schemas.incident import IncidentContext


def extract_features(incident: IncidentContext, action: ProposedAction) -> dict[str, float]:
    raise NotImplementedError(
        "features.extract_features is Phase P3 work. See ARCHITECTURE_BLUEPRINT.md §6.2."
    )
