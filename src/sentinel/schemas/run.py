# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# StepRecord (one propose/verify/act step) and RunRecord (a whole incident run).
# These are the rows stored in DuckDB and returned by the /api/runs endpoints.
"""Persistence-row contracts. Every orchestrator run and step becomes one of these, written to
DuckDB by store/duckdb_store.py (Phase P2+). Per CLAUDE.md: "no experiment result exists unless it's
a RunRecord row in DuckDB."
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from sentinel.schemas.action import ExecutionResult, ProposedAction
from sentinel.schemas.verdict import Verdict


class StepRecord(BaseModel):
    """One iteration of the orchestrator loop (propose -> verify -> act/revise/escalate)."""

    step_idx: int = Field(ge=0)
    proposed: ProposedAction
    verdict: Verdict
    result: ExecutionResult | None = None
    tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0.0)
    ground_truth_label: Literal["correct", "ineffective", "destructive", "out_of_envelope"] | None = Field(
        default=None,
        description="Eval-only label (labeling/oracle_labeler.py), attached by the orchestrator AFTER the "
        "verdict is final -- never visible to the agent or any verifier. eval/metrics.py reads it for "
        "bad-action-prevented and false-block rates. None = no label derivable (needs human review).",
    )


class RunRecord(BaseModel):
    """One full incident run: incident_id x seed x config, reproducible via config_hash."""

    incident_id: str = Field(min_length=1)
    seed: int
    config_hash: str = Field(min_length=1, description="hash of the resolved run config")
    steps: list[StepRecord] = Field(default_factory=list)
    final_resolved: bool
    unsafe_action_reached_exec: bool = Field(
        description="The key safety metric: did any destructive-labeled action ever reach "
        "executor.run(dry_run=False)?"
    )
    mttm_ms: float | None = Field(default=None, description="mean time-to-mitigation")
    total_tokens: int = Field(ge=0, default=0)
    total_cost_usd: float = Field(ge=0.0, default=0.0)
