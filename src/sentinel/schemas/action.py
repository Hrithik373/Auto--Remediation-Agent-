"""Action-side contracts: what the diagnosis agent proposes and what the executor reports back.

See ARCHITECTURE_BLUEPRINT.md §4. `action_type` values are validated against
config/action_envelope.yaml by verifier/envelope.py — this schema itself stays permissive (any
string) so the envelope config, not the schema, is the single source of truth for the allow-list.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProposedAction(BaseModel):
    """A single remediation action proposed by the diagnosis agent. Untrusted until verified."""

    action_type: str = Field(min_length=1)
    target: str = Field(min_length=1, description="service / pod / namespace / resource")
    params: dict = Field(default_factory=dict)
    rationale: str = Field(description="agent's justification")
    predicted_effect: str = Field(description="what the agent thinks will happen")


class ExecutionResult(BaseModel):
    """Outcome of handing a ProposedAction to executor.run() (Phase P1)."""

    executed: bool
    dry_run: bool
    resolved: bool | None = Field(default=None, description="from env oracle; None if not executed")
    side_effects: list[str] = Field(default_factory=list)
    error: str | None = None
