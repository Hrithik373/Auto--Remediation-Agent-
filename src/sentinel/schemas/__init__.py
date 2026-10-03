"""Pydantic v2 contracts every cross-module payload in sentinel-remediate must use.

Per CLAUDE.md: "No loose dicts across module boundaries." These four modules are frozen in Phase P0
(blueprint §4) — later phases consume them, they don't change their shape.
"""

from sentinel.schemas.action import ExecutionResult, ProposedAction
from sentinel.schemas.incident import IncidentContext, Telemetry
from sentinel.schemas.run import RunRecord, StepRecord
from sentinel.schemas.verdict import LayerVerdict, Verdict

__all__ = [
    "Telemetry",
    "IncidentContext",
    "ProposedAction",
    "ExecutionResult",
    "Verdict",
    "LayerVerdict",
    "StepRecord",
    "RunRecord",
]
