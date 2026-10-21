# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# The assistant's READ-ONLY tools: docs search, incidents, envelope rules, scenario judgement, run steps.
# Shared by the LLM tool loop and the offline router, so both modes answer from the same facts.
"""Assistant tool registry (ASSISTANT_BLUEPRINT.md §3, §4).

Every tool reads; none writes. evaluate_scenario runs the verifier policy's verify() only (see
scenarios.py). A tool returns a ToolResult: `text` is what the LLM (or the offline answer) sees,
`summary` is the one-line trace shown in the console, and structured payloads (judgement,
explanation, citations) travel alongside so the UI never has to parse prose.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from sentinel.assistant.explain import assess, explain_verdict, render_text
from sentinel.assistant.knowledge import KnowledgeBase, excerpt
from sentinel.assistant.scenarios import ScenarioEvaluator, UnknownIncident
from sentinel.context.builder import build_context
from sentinel.env.offline_adapter import OfflineEnvAdapter
from sentinel.schemas.assistant import Citation, ScenarioJudgement, ScenarioRequest, VerdictExplanation
from sentinel.schemas.run import RunRecord


class ToolError(Exception):
    pass


# Required params that, when a chat question leaves them out, are naturally the action's target.
_TARGET_PARAMS = frozenset({"service", "deployment", "pod_name", "node_name", "configmap"})


@dataclass
class ToolResult:
    text: str
    summary: str
    citations: list[Citation] = field(default_factory=list)
    judgement: ScenarioJudgement | None = None
    explanation: VerdictExplanation | None = None


@dataclass
class AssistantContext:
    """Everything the tools may read. `find_run` returns (run, metadata) for a stored or live run."""

    config: dict
    kb: KnowledgeBase
    scenarios: ScenarioEvaluator
    env: OfflineEnvAdapter
    envelope_path: Path
    results_path: Path
    find_run: Callable[[str], tuple[RunRecord, dict] | None] = lambda run_id: None
    list_runs: Callable[[], list[tuple[str, RunRecord]]] = list


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: str
    fn: Callable[[AssistantContext, dict], ToolResult]


def _require(args: dict, *names: str) -> None:
    missing = [n for n in names if args.get(n) in (None, "")]
    if missing:
        raise ToolError(f"missing argument(s): {', '.join(missing)}")


def search_docs(ctx: AssistantContext, args: dict) -> ToolResult:
    _require(args, "query")
    hits = ctx.kb.search(str(args["query"]), k=int(args.get("k", 3)))
    if not hits:
        return ToolResult("No matching documentation found.", "no doc matches")
    cites = [Citation(source=d.source, excerpt=excerpt(d, str(args["query"]))) for d, _ in hits]
    text = "\n\n".join(f"[{c.source}] {c.excerpt}" for c in cites)
    return ToolResult(text, f"{len(cites)} doc snippet(s): " + ", ".join(c.source for c in cites), cites)


def list_incidents(ctx: AssistantContext, args: dict) -> ToolResult:
    rows = []
    for incident_id in ctx.env.list_incidents():
        inc = ctx.env.get_incident(incident_id)
        alerts = "; ".join(
            f"{a.get('name', '?')} on {a.get('target', '?')}" for a in inc.telemetry.alerts[:2]
        )
        rows.append(f"- {incident_id}: {alerts or 'no alerts'}")
    return ToolResult("\n".join(rows), f"{len(rows)} incidents")


def get_incident(ctx: AssistantContext, args: dict) -> ToolResult:
    _require(args, "incident_id")
    incident_id = str(args["incident_id"])
    if incident_id not in ctx.env.list_incidents():
        raise ToolError(f"unknown incident {incident_id!r}")
    incident = ctx.env.get_incident(incident_id)
    # Observable telemetry only -- build_context never renders the ground-truth fault_family.
    text = build_context(incident.model_copy(update={"budget_tokens": 1500}))
    return ToolResult(text, f"telemetry summary for {incident_id}")


def envelope_rules(ctx: AssistantContext, args: dict) -> ToolResult:
    with ctx.envelope_path.open(encoding="utf-8") as f:
        envelope = yaml.safe_load(f)
    actions = envelope["allowed_actions"]
    policy = envelope.get("policy", {})
    wanted = args.get("action_type")
    if wanted:
        spec = actions.get(wanted)
        if spec is None:
            text = (
                f"'{wanted}' is NOT on the allow-list, so the envelope blocks it every time "
                "(out_of_envelope). "
                f"Allowed types: {', '.join(actions)}."
            )
            return ToolResult(text, f"{wanted}: not allow-listed")
        params = ", ".join(
            f"{p}{'' if r.get('required') else '?'}: {r.get('type', 'string')}"
            for p, r in spec.get("params", {}).items()
        )
        text = (
            f"{wanted}: scope={spec.get('scope')}, blast_radius={spec.get('blast_radius')}, "
            f"reversible={spec.get('reversible')}, params {{{params}}}. "
            f"Policy cap: blast_radius <= {policy.get('max_allowed_blast_radius')}; "
            f"forbidden namespaces: {policy.get('forbidden_namespaces')}."
        )
        return ToolResult(text, f"envelope rules for {wanted}")
    lines = [
        f"- {n}: blast_radius={s.get('blast_radius')}, reversible={s.get('reversible')}"
        for n, s in actions.items()
    ]
    head = (
        f"The envelope allows {len(actions)} action types (cap: blast_radius <= "
        f"{policy.get('max_allowed_blast_radius')}; "
        f"forbidden namespaces: {policy.get('forbidden_namespaces')}):"
    )
    return ToolResult("\n".join([head, *lines]), f"{len(actions)} allow-listed action types")


def fill_required_params(
    ctx: AssistantContext, incident_id: str, action_type: str, target: str, params: dict
) -> tuple[dict, list[str]]:
    """Fill required params a chat question implies but didn't spell out: target-like params take the
    target, and namespace takes the incident's usual one. Returns (params, what was assumed). Without
    this, "can we cordon node-17?" would be judged as a malformed action instead of the real question."""
    with ctx.envelope_path.open(encoding="utf-8") as f:
        spec = yaml.safe_load(f)["allowed_actions"].get(action_type, {}).get("params", {})
    out, assumed = dict(params), []
    for name, rule in spec.items():
        if not rule.get("required") or out.get(name) not in (None, ""):
            continue
        if name in _TARGET_PARAMS:
            out[name] = target
            assumed.append(f"{name}={target}")
        elif name == "namespace" and incident_id in ctx.env.list_incidents():
            seen = Counter(
                a["params"]["namespace"]
                for a in ctx.env.labeled_actions(incident_id)
                if a["params"].get("namespace")
            )
            if seen:
                out[name] = seen.most_common(1)[0][0]
                assumed.append(f"namespace={out[name]} (the incident's usual namespace)")
    return out, assumed


def evaluate_scenario(ctx: AssistantContext, args: dict) -> ToolResult:
    _require(args, "incident_id", "action_type", "target")
    defaults = ctx.config.get("assistant", {})
    params, assumed = fill_required_params(
        ctx, str(args["incident_id"]), str(args["action_type"]), str(args["target"]), args.get("params") or {}
    )
    try:
        req = ScenarioRequest(
            incident_id=str(args["incident_id"]),
            action_type=str(args["action_type"]),
            target=str(args["target"]),
            params=params,
            variant=args.get("variant") or defaults.get("default_variant", "learned"),
            tau=float(args.get("tau", ctx.config["verifier"]["threshold"])),
        )
    except ValueError as exc:
        raise ToolError(f"invalid scenario: {exc}") from exc
    try:
        judgement = ctx.scenarios.evaluate(req)
    except UnknownIncident as exc:
        raise ToolError(str(exc)) from exc
    except FileNotFoundError as exc:
        raise ToolError(f"the '{req.variant}' variant is unavailable: {exc}") from exc
    used = f"Params used: {json.dumps(req.params)}" + (f" (assumed {', '.join(assumed)})" if assumed else "")
    head = f"Verdict from the real verifier policy (variant={req.variant}):"
    text = f"{used}\n{head}\n{render_text(judgement.explanation)}"
    summary = (
        f"{req.action_type} on {req.target} -> {judgement.verdict.decision} ({req.variant}, τ={req.tau})"
    )
    return ToolResult(text, summary, judgement=judgement, explanation=judgement.explanation)


def explain_step(ctx: AssistantContext, args: dict) -> ToolResult:
    _require(args, "run_id")
    found = ctx.find_run(str(args["run_id"]))
    if found is None:
        raise ToolError(f"unknown run {args['run_id']!r}")
    run, meta = found
    if not run.steps:
        raise ToolError(f"run {args['run_id']} has no steps")
    idx = int(args.get("step_idx", len(run.steps) - 1))
    if not 0 <= idx < len(run.steps):
        raise ToolError(f"run {args['run_id']} has steps 0..{len(run.steps) - 1}, not {idx}")
    step = run.steps[idx]
    tau = float(meta.get("tau", ctx.config["verifier"]["threshold"]))
    gt = assess(step.ground_truth_label, step.verdict.decision, "stored with the run")
    explanation = explain_verdict(step.verdict, tau, gt)
    a = step.proposed
    head = f"Run {args['run_id']} step {idx} on {run.incident_id}: {a.action_type} on {a.target} {a.params}"
    return ToolResult(
        f"{head}\n{render_text(explanation)}",
        f"step {idx} -> {step.verdict.decision}",
        explanation=explanation,
    )


def recent_runs(ctx: AssistantContext, args: dict) -> ToolResult:
    rows = ctx.list_runs()
    wanted = args.get("incident_id")
    rows = [(rid, r) for rid, r in rows if not wanted or r.incident_id == wanted][-10:]
    if not rows:
        return ToolResult("No console runs recorded yet.", "0 runs")
    lines = [
        f"- {rid}: {r.incident_id}, {len(r.steps)} step(s), decisions "
        f"{[s.verdict.decision for s in r.steps]}, resolved={r.final_resolved}"
        for rid, r in rows
    ]
    return ToolResult("\n".join(lines), f"{len(rows)} recent run(s)")


def eval_metrics(ctx: AssistantContext, args: dict) -> ToolResult:
    if not ctx.results_path.exists():
        return ToolResult("No evaluation results yet: run `make eval` first.", "no results.json")
    data = json.loads(ctx.results_path.read_text(encoding="utf-8"))

    def pct(x):
        return "n/a" if x is None else f"{100 * x:.0f}%"

    lines = [f"Evaluation '{data.get('experiment')}' ({data.get('n_runs')} runs). Per baseline:"]
    for b in data.get("baselines", []):
        lines.append(
            f"- {b['baseline']} ({b['variant']}): resolution {pct(b.get('resolution'))}, "
            f"bad actions prevented {pct(b.get('bad_action_prevented'))}, "
            f"false blocks {pct(b.get('false_block'))}, "
            f"unsafe executions {pct(b.get('unsafe_execution'))}"
        )
    lines.append("Definitions live in src/sentinel/eval/metrics.py.")
    return ToolResult(
        "\n".join(lines),
        f"{len(data.get('baselines', []))} baseline rows",
        [Citation(source=str(ctx.results_path.as_posix()), excerpt=lines[0])],
    )


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool("search_docs", "search the project's docs and module docstrings", '{"query": str}', search_docs),
        Tool("list_incidents", "list the incident ids with their first alerts", "{}", list_incidents),
        Tool(
            "get_incident",
            "observable telemetry summary of one incident",
            '{"incident_id": str}',
            get_incident,
        ),
        Tool(
            "envelope_rules",
            "the allow-list rules, optionally for one action type",
            '{"action_type"?: str}',
            envelope_rules,
        ),
        Tool(
            "evaluate_scenario",
            "run the REAL verifier policy on a hypothetical action (verify only, never executes)",
            '{"incident_id": str, "action_type": str, "target": str, "params"?: object, '
            '"variant"?: "none|envelope|llm_judge|learned|combined", "tau"?: number}',
            evaluate_scenario,
        ),
        Tool(
            "explain_step",
            "explain a stored run step's verdict",
            '{"run_id": str, "step_idx"?: int}',
            explain_step,
        ),
        Tool("recent_runs", "the latest console runs", '{"incident_id"?: str}', recent_runs),
        Tool("eval_metrics", "headline evaluation metrics per baseline", "{}", eval_metrics),
    ]
}


def run_tool(ctx: AssistantContext, name: str, args: dict) -> ToolResult:
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolError(f"unknown tool {name!r}; available: {', '.join(TOOLS)}")
    return tool.fn(ctx, args)
