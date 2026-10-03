"""Read/control API for the triage console (FRONTEND_BLUEPRINT.md §5). Not implemented yet -- see
PROGRESS.md. A FastAPI router mounted at /api by gateway/app.py once Phase P5c starts; all payloads
reuse schemas/ directly, no new shapes (frontend/src/api/types.ts is generated from those same
schemas, so drift here is drift there too).

Phase P2's orchestrator.loop.Orchestrator is what actually produces the StepRecords this router
streams -- until it exists, the frontend's MSW mock layer (frontend/src/mock/handlers.ts) simulates
this same contract so the console is fully demoable without a backend.
"""

from __future__ import annotations

from fastapi import APIRouter

from sentinel.schemas.incident import IncidentContext
from sentinel.schemas.run import RunRecord

router = APIRouter(prefix="/api")


@router.get("/incidents")
def list_incidents() -> list[dict]:
    """[{ incident_id, source, fault_family, n_alerts, status }] -- summaries for the queue table."""
    raise NotImplementedError("gateway.api.list_incidents is Phase P5c work. See FRONTEND_BLUEPRINT.md §5.1.")


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str) -> IncidentContext:
    raise NotImplementedError("gateway.api.get_incident is Phase P5c work. See FRONTEND_BLUEPRINT.md §5.1.")


@router.get("/config")
def get_config() -> dict:
    raise NotImplementedError("gateway.api.get_config is Phase P5c work. See FRONTEND_BLUEPRINT.md §5.1.")


@router.post("/runs")
def start_run(incident_id: str, verifier: str, tau: float, dry_run: bool) -> dict:
    """Kicks orchestrator.loop.Orchestrator.run() as a background task; returns {run_id} immediately.
    Golden rule (CLAUDE.md): dry_run=False still requires execution.auto_execute=true in config --
    this endpoint must not be a way around that gate.
    """
    raise NotImplementedError(
        "gateway.api.start_run is Phase P5c work. See FRONTEND_BLUEPRINT.md §5.1, §5.2."
    )


@router.get("/runs/{run_id}/stream")
def stream_run(run_id: str):
    """SSE: `event: step` (one StepRecord per orchestrator step) then `event: final` (RunRecord),
    which closes the stream. Push StepRecords onto an asyncio.Queue from the orchestrator's
    background task and drain it here (blueprint §5.2) -- do not poll the store.
    """
    raise NotImplementedError("gateway.api.stream_run is Phase P5c work. See FRONTEND_BLUEPRINT.md §5.2.")


@router.get("/runs")
def list_runs() -> list[RunRecord]:
    raise NotImplementedError("gateway.api.list_runs is Phase P5c work. See FRONTEND_BLUEPRINT.md §5.1.")


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> RunRecord:
    raise NotImplementedError("gateway.api.get_run is Phase P5c work. See FRONTEND_BLUEPRINT.md §5.1.")


@router.post("/runs/{run_id}/decision")
def submit_decision(run_id: str, step_idx: int, human_decision: str) -> dict:
    """Optional HITL override on a blocked/escalated step."""
    raise NotImplementedError(
        "gateway.api.submit_decision is Phase P5c work. See FRONTEND_BLUEPRINT.md §5.1."
    )


@router.get("/experiments/pareto")
def get_pareto(verifier: str | None = None) -> dict:
    raise NotImplementedError(
        "gateway.api.get_pareto is Phase P5d work. See FRONTEND_BLUEPRINT.md §5.1, eval/pareto.py."
    )


@router.get("/experiments/metrics")
def get_metrics() -> list[dict]:
    raise NotImplementedError(
        "gateway.api.get_metrics is Phase P5d work. See FRONTEND_BLUEPRINT.md §5.1, eval/metrics.py."
    )


@router.get("/experiments/prevention_partition")
def get_prevention_partition() -> list[dict]:
    """★ The thesis figure (blueprint §6.3): caught_by_envelope / caught_by_judge_only / missed, per
    baseline. Computed from eval/metrics.py's bad-action-prevented partition, not invented here.
    """
    raise NotImplementedError(
        "gateway.api.get_prevention_partition is Phase P5d work. See FRONTEND_BLUEPRINT.md §5.1, §6.3."
    )


@router.get("/experiments/ablations")
def get_ablations() -> list[dict]:
    raise NotImplementedError(
        "gateway.api.get_ablations is Phase P5d work. See FRONTEND_BLUEPRINT.md §5.1, eval/ablations.py."
    )
