# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Offline mode: a deterministic intent router that picks the assistant's tools from keywords and
# composes a templated answer. Always available -- no LLM, no network.
"""Offline intent router (ASSISTANT_BLUEPRINT.md §6).

Order: explain a run step -> judge a scenario -> metrics -> envelope rules -> runs -> incidents ->
docs search. It understands simple phrasing only ("would restart_service on cart be allowed for
itbench-sre-scenario-2?"); anything it can't pin down, it asks for instead of guessing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import yaml

from sentinel.assistant.tools import AssistantContext, ToolError, ToolResult, run_tool
from sentinel.schemas.assistant import ChatRequest, ToolCall

_WHY = re.compile(r"\b(why|explain|reason|how come)\b")
_STEP = re.compile(r"\bstep\s*#?\s*(\d+)")
_RUN_ID = re.compile(r"\b([0-9a-f]{12})\b")
_SCENARIO_NO = re.compile(r"\bscenario[\s-]*(\d+)\b")
_TAU = re.compile(r"(?:tau|τ)\s*(?:=|of|at)?\s*(0?\.\d+|1(?:\.0+)?|0)\b")
_TARGET = re.compile(r"\b(?:on|to|target(?:ing)?|against|of)\s+(?:the\s+)?['\"`]?([a-z0-9][\w.-]*)", re.I)
_NAMESPACE = re.compile(
    r"\bnamespace\s*[=:]?\s*['\"`]?([a-z0-9][\w-]*)|\bin\s+(?:the\s+)?([a-z0-9][\w-]*)\s+namespace"
)
_JSON = re.compile(r"\{.*\}", re.S)
_VARIANTS = ("combined", "llm_judge", "learned", "envelope", "none")
_NOT_TARGETS = {"the", "a", "an", "this", "that", "it", "incident", "scenario", "namespace", "tau"}


@dataclass
class OfflineAnswer:
    answer: str
    calls: list[ToolCall] = field(default_factory=list)
    results: list[ToolResult] = field(default_factory=list)


def _call(ctx: AssistantContext, out: OfflineAnswer, tool: str, args: dict) -> ToolResult | None:
    try:
        result = run_tool(ctx, tool, args)
    except ToolError as exc:
        out.calls.append(ToolCall(tool=tool, args=args, ok=False, summary=str(exc)))
        return None
    out.calls.append(ToolCall(tool=tool, args=args, ok=True, summary=result.summary))
    out.results.append(result)
    return result


def _incident(ctx: AssistantContext, text: str, req: ChatRequest) -> str | None:
    known = ctx.env.list_incidents()
    mentioned = [i for i in known if i.lower() in text]
    if mentioned:
        return max(mentioned, key=len)
    number = _SCENARIO_NO.search(text)
    if number and f"itbench-sre-scenario-{number.group(1)}" in known:
        return f"itbench-sre-scenario-{number.group(1)}"
    return req.incident_id


def _action_vocabulary(ctx: AssistantContext) -> list[str]:
    with ctx.envelope_path.open(encoding="utf-8") as f:
        allowed = list(yaml.safe_load(f)["allowed_actions"])
    seen = set(allowed)
    for incident_id in ctx.env.list_incidents():
        seen.update(a["action_type"] for a in ctx.env.labeled_actions(incident_id))
    return sorted(seen, key=len, reverse=True)  # longest first: "restart_service" before "restart"


def _action_type(ctx: AssistantContext, text: str) -> str | None:
    flat = re.sub(r"[\s-]+", "_", text)
    for action_type in _action_vocabulary(ctx):
        if action_type in flat:
            return action_type
    return None


def _target(text: str, action_type: str, incident_id: str | None) -> str | None:
    for m in _TARGET.finditer(text):
        word = m.group(1).strip(".,?!'\"`")
        if word.lower() in _NOT_TARGETS or word == action_type or word == incident_id:
            continue
        if incident_id and word in incident_id:
            continue
        return word
    return None


def _params(text: str) -> dict:
    """Params the user actually stated: a JSON object, or a namespace. evaluate_scenario fills the
    remaining required ones (and says what it assumed)."""
    raw = _JSON.search(text)
    if raw:
        try:
            parsed = json.loads(raw.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    ns = _NAMESPACE.search(text)
    return {"namespace": ns.group(1) or ns.group(2)} if ns else {}


def _scenario(
    ctx: AssistantContext, text: str, req: ChatRequest, out: OfflineAnswer, action_type: str
) -> OfflineAnswer:
    incident_id = _incident(ctx, text, req)
    if incident_id is None:
        out.answer = (
            f"Which incident should I judge `{action_type}` on? Name one (for example `pod-crashloop` or "
            "`itbench-sre-scenario-13`), open it in the console, or use the scenario form."
        )
        return out
    target = _target(text, action_type, incident_id)
    if target is None:
        out.answer = (
            f"What should `{action_type}` target on `{incident_id}`? For example: "
            f'"would {action_type} on <service> be allowed?". The scenario form takes exact params too.'
        )
        return out
    args = {"incident_id": incident_id, "action_type": action_type, "target": target, "params": _params(text)}
    tau = _TAU.search(text)
    if tau:
        args["tau"] = float(tau.group(1))
    variant = next((v for v in _VARIANTS if re.search(rf"\b{v}\b", text)), None)
    if variant:
        args["variant"] = variant
    result = _call(ctx, out, "evaluate_scenario", args)
    if result is None:
        out.answer = f"I couldn't evaluate that scenario: {out.calls[-1].summary}"
        return out
    lead = f"I ran the real verifier policy on `{action_type}` targeting `{target}` for `{incident_id}`."
    out.answer = f"{lead}\n\n{result.text}"
    return out


def _explain(ctx: AssistantContext, text: str, req: ChatRequest, out: OfflineAnswer) -> OfflineAnswer | None:
    run_id = (_RUN_ID.search(text).group(1) if _RUN_ID.search(text) else None) or req.run_id
    if run_id is None:
        return None
    step = _STEP.search(text)
    args: dict = {"run_id": run_id}
    if step:
        args["step_idx"] = int(step.group(1))
    elif req.step_idx is not None:
        args["step_idx"] = req.step_idx
    result = _call(ctx, out, "explain_step", args)
    out.answer = result.text if result else f"I couldn't explain that step: {out.calls[-1].summary}"
    return out


def _docs(ctx: AssistantContext, text: str, out: OfflineAnswer) -> OfflineAnswer:
    result = _call(ctx, out, "search_docs", {"query": text})
    if result is None or not result.citations:
        out.answer = (
            "I couldn't find that in the project docs. Try naming a component (envelope, LLM judge, learned "
            "verifier, orchestrator, executor, gateway) or ask whether a specific action would be allowed."
        )
        return out
    bullets = "\n\n".join(f"From {c.source}:\n{c.excerpt}" for c in result.citations)
    out.answer = f"Here is what the project documentation says:\n\n{bullets}"
    return out


def answer_offline(ctx: AssistantContext, req: ChatRequest) -> OfflineAnswer:
    text = req.messages[-1].content.strip().lower()
    out = OfflineAnswer(answer="")
    if _WHY.search(text) and (req.run_id or _RUN_ID.search(text)):
        explained = _explain(ctx, text, req, out)
        if explained is not None:
            return explained
    action_type = _action_type(ctx, text)
    if action_type and not re.search(r"\b(what is|what does|define)\b", text):
        return _scenario(ctx, text, req, out, action_type)
    if re.search(r"\b(metric|metrics|results?|false[- ]block|prevented|baseline|pareto|evaluation)\b", text):
        result = _call(ctx, out, "eval_metrics", {})
        docs = _call(ctx, out, "search_docs", {"query": text, "k": 1})
        out.answer = result.text if result else "No evaluation results are available."
        if docs and docs.citations:
            out.answer += f"\n\nFrom {docs.citations[0].source}:\n{docs.citations[0].excerpt}"
        return out
    if re.search(r"\b(envelope|allow[- ]?list|allowed actions|which actions)\b", text):
        result = _call(ctx, out, "envelope_rules", {"action_type": action_type} if action_type else {})
        out.answer = result.text if result else out.calls[-1].summary
        return out
    if re.search(r"\b(recent|latest|last)\s+runs?\b", text):
        result = _call(ctx, out, "recent_runs", {"incident_id": req.incident_id} if req.incident_id else {})
        out.answer = result.text if result else out.calls[-1].summary
        return out
    if re.search(r"\b(list|which|what|all)\b.*\bincidents\b", text):
        result = _call(ctx, out, "list_incidents", {})
        out.answer = (
            f"The offline environment has these incidents:\n{result.text}"
            if result
            else out.calls[-1].summary
        )
        return out
    incident_id = _incident(ctx, text, req)
    if incident_id and re.search(r"\b(incident|scenario|telemetry|happening|wrong|alert)\b", text):
        result = _call(ctx, out, "get_incident", {"incident_id": incident_id})
        if result:
            head = f"Observable telemetry for `{incident_id}` (what the agent and verifiers see):"
            out.answer = f"{head}\n\n{result.text}"
            return out
    return _docs(ctx, text, out)
