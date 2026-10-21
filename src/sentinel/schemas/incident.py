# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# IncidentContext and Telemetry: what an environment hands to the agent and the verifiers.
# fault_family is eval-only ground truth and is never shown to an LLM.
"""Incident-side contracts: what the env adapter hands to the diagnosis agent.

See ARCHITECTURE_BLUEPRINT.md §4.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Telemetry(BaseModel):
    """Raw observability signal for one incident, as pulled from the env adapter."""

    logs: list[str] = Field(default_factory=list)
    metrics: dict[str, list[float]] = Field(default_factory=dict, description="metric_name -> series")
    traces: list[dict] = Field(default_factory=list, description="span records")
    topology: dict = Field(default_factory=dict, description="service dependency graph")
    alerts: list[dict] = Field(default_factory=list)


class IncidentContext(BaseModel):
    """Everything the diagnosis agent (Phase P1) is given for one incident."""

    incident_id: str = Field(min_length=1)
    source: Literal["aiopslab", "itbench", "offline"]
    fault_family: str | None = Field(
        default=None,
        description="Ground-truth fault family. For eval/labeling only — never fed to the agent's "
        "prompt, or the diagnosis task becomes trivial.",
    )
    telemetry: Telemetry
    budget_tokens: int = Field(gt=0, description="Context compaction target (context/builder.py, Phase P1)")
