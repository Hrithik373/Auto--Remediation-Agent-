# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# The /api/assistant routes: chat with the explainer bot, judge a what-if scenario, explain a stored step.
# Read-only by construction: none of these routes can execute an action or change a stored run.
"""Assistant API (ASSISTANT_BLUEPRINT.md §7), mounted by gateway/app.py next to gateway/api.py.

Shares api.py's process state (config, store, live runs) so the assistant can explain a run the
console just streamed. The AssistantService itself is built lazily on first use: indexing the docs
and loading the learned model shouldn't slow the gateway's startup.
"""

from __future__ import annotations

from functools import lru_cache

import yaml
from fastapi import APIRouter, HTTPException

from sentinel.assistant.entities import incident_entities
from sentinel.assistant.scenarios import UnknownIncident
from sentinel.assistant.service import AssistantService, build_assistant
from sentinel.assistant.tools import ToolError
from sentinel.config import resolve_path
from sentinel.gateway.api import state
from sentinel.gateway.runs import CONSOLE_EXPERIMENT
from sentinel.schemas.assistant import (
    ActionSpec,
    AssistantInfo,
    ChatReply,
    ChatRequest,
    IncidentEntities,
    ParamSpec,
    ScenarioJudgement,
    ScenarioRequest,
    VerdictExplanation,
)
from sentinel.schemas.run import RunRecord

router = APIRouter(prefix="/api/assistant")


def _find_run(run_id: str) -> tuple[RunRecord, dict] | None:
    s = state()
    handle = s["runs"].get(run_id)
    if handle is not None and handle.final is not None:
        return handle.final, {"tau": handle.tau, "variant": handle.variant}
    run = s["store"].get_run(run_id)
    if run is None:
        return None
    return run, s["store"].get_run_meta(run_id) or {}


def _list_runs() -> list[tuple[str, RunRecord]]:
    return state()["store"].read_runs_with_ids(experiment=CONSOLE_EXPERIMENT)


@lru_cache(maxsize=1)
def assistant() -> AssistantService:
    return build_assistant(state()["config"], find_run=_find_run, list_runs=_list_runs)


def _actions() -> list[ActionSpec]:
    path = resolve_path(state()["config"]["verifier"]["envelope_config"])
    with path.open(encoding="utf-8") as f:
        allowed = yaml.safe_load(f)["allowed_actions"]
    return [
        ActionSpec(
            action_type=name,
            scope=spec.get("scope"),
            blast_radius=spec.get("blast_radius"),
            reversible=spec.get("reversible"),
            params={
                p: ParamSpec(type=str(rule.get("type", "string")), required=bool(rule.get("required")))
                for p, rule in spec.get("params", {}).items()
            },
        )
        for name, spec in allowed.items()
    ]


@router.get("/info")
def info() -> AssistantInfo:
    svc = assistant()
    return AssistantInfo(
        mode=svc.mode,
        notice=svc.unavailable_reason,
        default_variant=state()["config"].get("assistant", {}).get("default_variant", "learned"),
        actions=_actions(),
    )


@router.get("/entities/{incident_id}")
def entities(incident_id: str) -> IncidentEntities:
    """Dropdown choices for the scenario form (entity names + candidate param values, no labels)."""
    s = state()
    if incident_id not in s["env"].list_incidents():
        raise HTTPException(status_code=404, detail=f"unknown incident {incident_id!r}")
    return incident_entities(s["env"], resolve_path(s["config"]["verifier"]["envelope_config"]), incident_id)


@router.post("/chat")
def chat(body: ChatRequest) -> ChatReply:
    return assistant().chat(body)


@router.post("/scenario")
def scenario(body: ScenarioRequest) -> ScenarioJudgement:
    try:
        return assistant().scenario(body)
    except UnknownIncident as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:  # learned model not trained yet
        raise HTTPException(status_code=409, detail=f"verifier variant unavailable: {exc}") from exc


@router.get("/explain/{run_id}/{step_idx}")
def explain(run_id: str, step_idx: int) -> VerdictExplanation:
    try:
        return assistant().explain(run_id, step_idx)
    except ToolError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def reset_assistant_for_tests() -> None:
    assistant.cache_clear()
