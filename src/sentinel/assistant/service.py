# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# AssistantService: answers chat (LLM tool loop, or the offline router as fallback), judges scenarios
# and explains stored steps. The single entry point the gateway's /api/assistant routes call.
"""AssistantService (ASSISTANT_BLUEPRINT.md §4, §6).

Mode choice: LLM mode when `assistant.enabled_llm` is true and the provider's credentials are present;
any LLM failure falls back to the offline router for that message, with a `notice` saying why. The
reply's judgement / explanation / citations always come from tool results, never from LLM prose.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from sentinel.assistant.knowledge import KnowledgeBase
from sentinel.assistant.loop import LoopOutcome, ToolLoop
from sentinel.assistant.router import answer_offline
from sentinel.assistant.scenarios import ScenarioEvaluator
from sentinel.assistant.tools import AssistantContext, ToolError, ToolResult, run_tool
from sentinel.config import resolve_path
from sentinel.env.offline_adapter import OfflineEnvAdapter
from sentinel.gateway.clients import LLMClient, build_llm_client
from sentinel.schemas.assistant import (
    ChatReply,
    ChatRequest,
    ScenarioJudgement,
    ScenarioRequest,
    VerdictExplanation,
)
from sentinel.schemas.run import RunRecord

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DOCS = [
    "ARCHITECTURE_BLUEPRINT.md",
    "FRONTEND_BLUEPRINT.md",
    "ASSISTANT_BLUEPRINT.md",
    "README.md",
    "PROGRESS.md",
]
_DECISION_WORDS = {"allow": ("allow",), "block": ("block",), "revise": ("revis",)}


def _context_note(req: ChatRequest) -> str:
    parts = [
        f"{k}={v}"
        for k, v in (("incident_id", req.incident_id), ("run_id", req.run_id), ("step_idx", req.step_idx))
        if v is not None
    ]
    return "console context: " + ", ".join(parts) if parts else ""


def _merge(answer: str, mode: str, results: list[ToolResult], calls, notice: str | None) -> ChatReply:
    judgement = next((r.judgement for r in reversed(results) if r.judgement is not None), None)
    explanation = next((r.explanation for r in reversed(results) if r.explanation is not None), None)
    citations = [c for r in results for c in r.citations]
    if explanation is not None:
        # The verdict is authoritative: if the prose never states it, lead with the policy's headline.
        stems = _DECISION_WORDS[explanation.decision]
        if not any(s in answer.lower() for s in stems):
            answer = f"{explanation.headline}\n\n{answer}"
    return ChatReply(
        answer=answer,
        mode=mode,
        tool_calls=calls,
        citations=citations,
        judgement=judgement,
        explanation=explanation,
        notice=notice,
    )


class AssistantService:
    def __init__(
        self, ctx: AssistantContext, loop: ToolLoop | None = None, *, unavailable_reason: str | None = None
    ) -> None:
        self.ctx = ctx
        self._loop = loop
        self._unavailable = unavailable_reason

    @property
    def mode(self) -> str:
        return "llm" if self._loop is not None else "offline"

    @property
    def unavailable_reason(self) -> str | None:
        """Why LLM mode is off (missing key, disabled), or None."""
        return self._unavailable

    def chat(self, req: ChatRequest) -> ChatReply:
        notice = None
        if self._loop is not None:
            try:
                outcome: LoopOutcome = self._loop.run(self.ctx, req.messages, _context_note(req))
                return _merge(outcome.answer, "llm", outcome.results, outcome.calls, None)
            except Exception as exc:  # provider down, rate limit, unparseable loop -> answer offline
                notice = (
                    f"The LLM was unavailable ({type(exc).__name__}), so this answer comes from offline mode."
                )
        elif self._unavailable:
            notice = self._unavailable
        offline = answer_offline(self.ctx, req)
        return _merge(offline.answer, "offline", offline.results, offline.calls, notice)

    def scenario(self, req: ScenarioRequest) -> ScenarioJudgement:
        return self.ctx.scenarios.evaluate(req)

    def explain(self, run_id: str, step_idx: int) -> VerdictExplanation:
        result = run_tool(self.ctx, "explain_step", {"run_id": run_id, "step_idx": step_idx})
        if result.explanation is None:
            raise ToolError(f"no explanation for run {run_id} step {step_idx}")
        return result.explanation


def _llm_unavailable(config: dict, provider: str | None) -> str | None:
    """Why LLM mode can't work (a missing key), or None if it might."""
    name = provider or "anthropic"
    spec = config.get("llm_providers", {}).get(name, {"kind": "anthropic"} if name == "anthropic" else None)
    if spec is None:
        return f"LLM provider '{name}' is not configured, so answers come from offline mode."
    key_env = spec.get("api_key_env") or ("ANTHROPIC_API_KEY" if spec["kind"] == "anthropic" else None)
    if key_env and not os.environ.get(key_env):
        return f"{key_env} is not set, so answers come from offline mode."
    return None


def build_assistant(
    config: dict,
    *,
    find_run: Callable[[str], tuple[RunRecord, dict] | None] = lambda run_id: None,
    list_runs: Callable[[], list[tuple[str, RunRecord]]] = list,
    llm: LLMClient | None = None,
    scenarios: ScenarioEvaluator | None = None,
) -> AssistantService:
    settings = config.get("assistant", {})
    env = OfflineEnvAdapter(resolve_path(config.get("env", {}).get("fixtures_dir", "fixtures/incidents")))
    ctx = AssistantContext(
        config=config,
        kb=KnowledgeBase.from_repo(REPO_ROOT, settings.get("docs", DEFAULT_DOCS)),
        scenarios=scenarios or ScenarioEvaluator(config),
        env=env,
        envelope_path=resolve_path(config["verifier"]["envelope_config"]),
        results_path=resolve_path(settings.get("results_path", "runs/eval/results.json")),
        find_run=find_run,
        list_runs=list_runs,
    )
    models = config.get("models", {})
    reason = None
    if llm is None and settings.get("enabled_llm", True):
        reason = _llm_unavailable(config, models.get("assistant_provider"))
        if reason is None:
            # Interactive: give up fast on rate limits and answer offline rather than make the user wait.
            http_opts = {
                "timeout_s": settings.get("llm_timeout_s", 30),
                "max_retries": settings.get("llm_max_retries", 1),
            }
            llm = build_llm_client(config, provider=models.get("assistant_provider"), http_opts=http_opts)
    elif not settings.get("enabled_llm", True):
        reason = "LLM mode is disabled (assistant.enabled_llm=false); answers come from offline mode."
    loop = (
        ToolLoop(
            llm,
            model=models.get("assistant", models.get("llm_judge", "")),
            max_tool_calls=settings.get("max_tool_calls", 5),
            max_tokens=settings.get("max_tokens", 1500),
        )
        if llm is not None
        else None
    )
    return AssistantService(ctx, loop, unavailable_reason=reason)
