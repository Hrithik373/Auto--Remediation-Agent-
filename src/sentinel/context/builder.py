"""Context compaction/token-budgeting/redaction for the diagnosis agent — Phase P1.

Intended behavior (blueprint §3): compact an IncidentContext's Telemetry down to
IncidentContext.budget_tokens, selecting the most relevant logs/metrics/traces/topology via
context/retrievers.py, and redact anything sensitive before it reaches the LLM.
"""

from __future__ import annotations

from sentinel.schemas.incident import IncidentContext


def build_context(incident: IncidentContext) -> str:
    raise NotImplementedError(
        "context.builder.build_context is Phase P1 work. See ARCHITECTURE_BLUEPRINT.md §3."
    )
