"""Read/control API for the triage console (FRONTEND_BLUEPRINT.md §5), mounted at /api by gateway/app.py.

Payloads reuse schemas/ (IncidentContext, StepRecord, RunRecord); the experiment endpoints serve
eval/report.py's tables, rebuilt from the same DuckDB rows `make eval` writes -- the console and the
report cannot disagree. Config comes from $SENTINEL_CONFIG (an overlay on config/default.yaml).

Golden rule (CLAUDE.md): POST /runs with dry_run=false is refused unless the loaded config has
execution.auto_execute=true. This endpoint is never a way around that gate.
"""

from __future__ import annotations

import asyncio
import json
import os
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from sentinel.config import load_config, resolve_path
from sentinel.env.offline_adapter import OfflineEnvAdapter
from sentinel.eval.report import build_results
from sentinel.gateway.runs import CONSOLE_EXPERIMENT, RunManager
from sentinel.observability.metrics import init_metrics, run_outcome
from sentinel.schemas.incident import IncidentContext
from sentinel.schemas.run import RunRecord, StepRecord
from sentinel.store.duckdb_store import DuckDBStore

router = APIRouter(prefix="/api")
SSE_WAIT_S = 15.0  # heartbeat interval while a run is between steps


class StartRun(BaseModel):
    incident_id: str
    verifier: Literal["none", "envelope", "llm_judge", "learned", "combined"] = "combined"
    tau: float = Field(default=0.5, ge=0.0, le=1.0)
    dry_run: bool = True


class HumanDecision(BaseModel):
    step_idx: int = Field(ge=0)
    human_decision: Literal["approve", "reject"]


@lru_cache(maxsize=1)
def state() -> dict:
    """Process-wide config, store, env and run manager (built lazily, on first request)."""
    overlay = os.environ.get("SENTINEL_CONFIG")
    config = load_config(resolve_path(overlay) if overlay else None)
    store = DuckDBStore(resolve_path(config["store"]["path"]))

    def load_learned():
        from sentinel.verifier.learned import LearnedVerifier

        return LearnedVerifier(model_path=resolve_path(config["verifier"]["learned_model_path"]))

    return {
        "config": config,
        "store": store,
        "env": OfflineEnvAdapter(),
        "runs": RunManager(config, store, init_metrics(), learned_loader=load_learned),
    }


# -- incidents / config ---------------------------------------------------------------------------


def _status(store: DuckDBStore) -> dict[str, str]:
    """Latest console outcome per incident -> queue status."""
    status = {}
    for _, run in store.read_runs_with_ids(experiment=CONSOLE_EXPERIMENT):
        status[run.incident_id] = {"resolved": "resolved", "escalated": "blocked"}.get(
            run_outcome(run), "escalated"
        )
    return status


@router.get("/incidents")
def list_incidents() -> list[dict]:
    s = state()
    status = _status(s["store"])
    out = []
    for incident_id in s["env"].list_incidents():
        inc = s["env"].get_incident(incident_id)
        out.append(
            {
                "incident_id": incident_id,
                "source": inc.source,
                "fault_family": inc.fault_family or "unknown",
                "n_alerts": len(inc.telemetry.alerts),
                "status": status.get(incident_id, "queued"),
            }
        )
    return out


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str) -> IncidentContext:
    try:
        return state()["env"].get_incident(incident_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"unknown incident {incident_id!r}") from exc


@router.get("/config")
def get_config() -> dict:
    c = state()["config"]
    return {
        "models": {k: v for k, v in c["models"].items() if k != "max_tokens_per_call"},
        "verifier_choice": c["verifier"]["active"],
        "tau": c["verifier"]["threshold"],
        "auto_execute": bool(c["execution"]["auto_execute"]),
        "max_steps": c["budgets"]["max_steps"],
        "agent_kind": c["agent"]["kind"],
        "on_block": c["orchestrator"].get("on_block", "escalate"),
    }


# -- runs -----------------------------------------------------------------------------------------


@router.post("/runs")
def start_run(body: StartRun) -> dict:
    s = state()
    if body.incident_id not in s["env"].list_incidents():
        raise HTTPException(status_code=404, detail=f"unknown incident {body.incident_id!r}")
    if not body.dry_run and not s["config"]["execution"]["auto_execute"]:
        raise HTTPException(
            status_code=403,
            detail="real (non-dry-run) execution requires execution.auto_execute="
            "true in the gateway's config (SENTINEL_CONFIG); dry_run=true is always allowed",
        )
    try:
        handle = s["runs"].start(body.incident_id, body.verifier, body.tau, body.dry_run)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"run_id": handle.run_id}


def _sse(kind: str, payload: object) -> str:
    data = (
        payload.model_dump_json() if hasattr(payload, "model_dump_json") else json.dumps({"error": payload})
    )
    return f"event: {kind}\ndata: {data}\n\n"


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str) -> StreamingResponse:
    handle = state()["runs"].get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail=f"unknown or expired run {run_id!r}")

    async def events():
        index = 0
        while True:
            event = await asyncio.to_thread(handle.wait_for, index, SSE_WAIT_S)
            if event is None:
                yield ": keep-alive\n\n"
                continue
            index += 1
            yield _sse(*event)
            if event[0] in ("final", "error"):
                return

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/runs")
def list_runs(limit: int = Query(default=50, ge=1, le=500)) -> list[RunRecord]:
    rows = state()["store"].read_runs_with_ids(experiment=CONSOLE_EXPERIMENT)
    return [run for _, run in rows[::-1][:limit]]


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> RunRecord:
    s = state()
    handle = s["runs"].get(run_id)
    run = (handle.final if handle else None) or s["store"].get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"unknown run {run_id!r} (or still running)")
    return run


@router.post("/runs/{run_id}/decision")
def submit_decision(run_id: str, body: HumanDecision) -> StepRecord:
    """Records a human's approve/reject on a step for the audit trail. It does NOT execute anything:
    acting on a human approval would be a path to the executor outside verifier.policy (CLAUDE.md)."""
    run = get_run(run_id)
    if body.step_idx >= len(run.steps):
        raise HTTPException(status_code=404, detail=f"run {run_id} has no step {body.step_idx}")
    state()["store"].record_human_decision(run_id, body.step_idx, body.human_decision)
    return run.steps[body.step_idx]


# -- experiments (read-only views of `make eval`'s DuckDB rows) -------------------------------------


def _db_version(store: DuckDBStore) -> float:
    return store.path.stat().st_mtime if store.path.exists() else 0.0


@lru_cache(maxsize=4)
def _results(experiment: str, db_version: float) -> dict:
    s = state()
    del db_version  # cache key only: any write to the store invalidates
    return build_results(
        s["store"],
        experiment,
        resamples=200,
        seed=s["config"]["orchestrator"]["seed"],
        models_dir=resolve_path(s["config"]["verifier"]["learned_model_path"]).parent,
    )


def results() -> dict:
    s = state()
    return _results(s["config"]["eval"]["experiment"], _db_version(s["store"]))


@router.get("/experiments/pareto")
def get_pareto(verifier: str | None = None) -> dict[str, list[dict]]:
    series = results()["pareto"]
    return {verifier: series[verifier]} if verifier in series else series


@router.get("/experiments/metrics")
def get_metrics() -> list[dict]:
    return [
        {
            "baseline": b["baseline"],
            "variant": b["variant"],
            "resolution": b["resolution"],
            "bad_prevented": b["bad_action_prevented"],
            "false_block": b["false_block"],
            "unsafe_execution": b["unsafe_execution"],
            "mttm_ms": b["mttm_ms"],
            "cost_usd": b["cost_usd"],
        }
        for b in results()["baselines"]
    ]


@router.get("/experiments/prevention_partition")
def get_prevention_partition() -> list[dict]:
    """★ The thesis figure: caught_by_envelope / caught_by_secondary_only / missed, per baseline."""
    return results()["prevention_partition"]


@router.get("/experiments/ablations")
def get_ablations() -> list[dict]:
    return results()["ablations"]


def reset_state_for_tests() -> None:
    state.cache_clear()
    _results.cache_clear()
