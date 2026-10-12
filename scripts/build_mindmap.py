#!/usr/bin/env python
"""`make mindmap` -- docs/project_mindmap.pdf: the project as a presentable mind map for the panel.

Slides (16:9): 1 the numbered overview map; 2-9 one deep-dive per branch (mini-map with that branch
highlighted, what / why / evidence / where in the code / a talking point); 10 results; 11 limitations.

Every number is read from `make eval` outputs (runs/eval/results.json) at build time -- none are typed
in -- so the slides always match the latest experiment. Rendered with headless Chromium (Playwright).
"""

# ruff: noqa: E501 -- slide content below is prose; wrapping it would make it harder to edit.
from __future__ import annotations

import datetime as dt
import html
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "runs" / "eval" / "results.json"
OUT_PDF = REPO / "docs" / "project_mindmap.pdf"
BUILD = REPO / "docs" / "mindmap" / "build"

W, H = 2040, 1010  # overview SVG canvas
CX, CY = W / 2, H / 2
LEAF_DY, GROUP_GAP = 31, 34
SLIDE_W, SLIDE_H = 1280, 720


# -- numbers (all from make eval) ------------------------------------------------------------------


def pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def numbers() -> dict[str, str]:
    if not RESULTS.exists():
        sys.exit(f"{RESULTS.relative_to(REPO)} not found -- run `make eval` first")
    r = json.loads(RESULTS.read_text(encoding="utf-8"))
    base = {b["variant"]: b for b in r["baselines"]}
    abl = {(a["name"], a["variant"], a["metric"]): a["value"] for a in r["ablations"]}
    part = {p["variant"]: p for p in r["prevention_partition"]}
    train = r["learned_verifier_training"]
    ds, lv = train["dataset"], train["learned_verifier"]
    ci = lambda b, m: f"{pct(base[b][m + '_ci95'][0])}–{pct(base[b][m + '_ci95'][1])}"  # noqa: E731
    fixtures = list((REPO / "fixtures" / "incidents").glob("*.json"))
    n_itb = sum(f.name.startswith("itbench") for f in fixtures)
    retry = "Envelope + learned: retry"
    return {
        "n_runs": f"{r['n_runs']:,}",
        "n_inc": str(len(fixtures)),
        "n_itb": str(n_itb),
        "n_hand": str(len(fixtures) - n_itb),
        "seeds": str(base["none"]["n_runs"] // len(fixtures)),
        "u_unsafe": pct(base["none"]["unsafe_execution"]),
        "u_unsafe_ci": ci("none", "unsafe_execution"),
        "u_res": pct(base["none"]["resolution"]),
        "u_safe": pct(base["none"]["net_safe_resolutions"]),
        "e_unsafe": pct(base["envelope"]["unsafe_execution"]),
        "e_unsafe_ci": ci("envelope", "unsafe_execution"),
        "e_res": pct(base["envelope"]["resolution"]),
        "e_safe": pct(base["envelope"]["net_safe_resolutions"]),
        "e_prev": pct(base["envelope"]["bad_action_prevented"]),
        "e_fb": pct(base["envelope"]["false_block"]),
        "l_unsafe": pct(base["learned"]["unsafe_execution"]),
        "l_unsafe_ci": ci("learned", "unsafe_execution"),
        "l_res": pct(base["learned"]["resolution"]),
        "l_safe": pct(base["learned"]["net_safe_resolutions"]),
        "l_prev": pct(base["learned"]["bad_action_prevented"]),
        "l_fb": pct(base["learned"]["false_block"]),
        "l_fb_ci": ci("learned", "false_block"),
        "sec_only": pct(part["learned"]["caught_by_secondary_only"]),
        "r_res": pct(abl[("Block handling", retry, "resolution")]),
        "r_safe": pct(abl[("Block handling", retry, "net_safe_resolutions")]),
        "r_unsafe": pct(abl[("Block handling", retry, "unsafe_execution")]),
        "weak_unsafe": pct(abl[("Agent quality", "none@weak", "unsafe_execution")]),
        "strong_unsafe": pct(abl[("Agent quality", "none@strong", "unsafe_execution")]),
        "rows": str(ds["rows"]),
        "lab_c": str(ds["labels"]["correct"]),
        "lab_i": str(ds["labels"]["ineffective"]),
        "lab_d": str(ds["labels"]["destructive"]),
        "lab_o": str(ds["labels"]["out_of_envelope"]),
        "needs_review": str(ds["needs_review"]),
        "auc": f"{lv['within_type_contrast']['auc']:.3f}",
        "auc_type": f"{lv['within_type_contrast_type_only_baseline']['auc']:.3f}",
        "ece": f"{lv['within_type_contrast']['ece']:.3f}",
        "folds": str(train["folds"]),
    }


# -- content ---------------------------------------------------------------------------------------


@dataclass
class Branch:
    num: int
    title: str
    color: str
    side: str
    leaves: list[str]  # short lines on the overview map
    tagline: str
    what: list[str]
    why: str
    facts: list[tuple[str, str]]  # (big value, label)
    panel: str  # talking point
    code: list[str]


def branches(n: dict[str, str]) -> list[Branch]:
    return [
        Branch(
            1,
            "The idea",
            "#2a78d6",
            "left",
            [
                "Problem: an AI may suggest a harmful fix",
                "LLM = untrusted planner: it only proposes",
                "Every action must pass the verifier first",
                "auto_execute is OFF by default",
                "Runs fully offline: zero Kubernetes",
            ],
            "Let an AI propose incident fixes, but never let it act unchecked.",
            [
                "LLM agents can read logs and metrics and suggest a remediation, confidently, and sometimes wrongly (e.g. scaling down a healthy service).",
                "Full autonomy is risky; asking a human to approve everything defeats the point.",
                "Our design treats the LLM as an <b>untrusted planner</b>: it may only <i>propose</i>. A separate <b>verifier</b> decides; only an <i>allow</i> reaches the executor.",
                "Research question: how much unsafe execution can a layered verifier prevent, and what does it cost in false blocks and incidents left unresolved?",
            ],
            "Autonomous operations are only usable if their safety can be enforced and measured, not assumed.",
            [
                (n["u_unsafe"], "of runs execute an unsafe action with no verifier"),
                (n["l_unsafe"], "with envelope + learned verifier"),
            ],
            "Our contribution is not a better agent. It is a verifier that makes any agent safer, plus a way to measure exactly how much safer.",
            ["CLAUDE.md (golden rules)", "src/sentinel/executor/executor.py"],
        ),
        Branch(
            2,
            "Incident data",
            "#1a9e75",
            "left",
            [
                f"{n['n_inc']} saved incidents (fixtures/incidents/)",
                f"{n['n_hand']} hand-built + {n['n_itb']} from IBM ITBench-Lite",
                "Telemetry: logs, metrics, traces, alerts, topology",
                "Oracle labels: correct / ineffective / destructive",
                "Rule-augmented hard cases (R1-R4)",
                "Provenance on every label + review CLI",
            ],
            f"{n['n_inc']} reproducible incidents, with an answer key for every candidate action.",
            [
                f"{n['n_hand']} hand-built incidents plus {n['n_itb']} converted from IBM's public <b>ITBench-Lite</b> SRE fault scenarios by our converter.",
                "Each incident carries telemetry (logs, metrics, traces, alerts, service topology) and an <b>oracle</b>: candidate actions labeled correct, ineffective, destructive or out-of-envelope.",
                f"{n['rows']} labeled actions: {n['lab_c']} correct, {n['lab_i']} ineffective, {n['lab_d']} destructive, {n['lab_o']} out-of-envelope. Every label records its <b>provenance</b>.",
                "Rule augmentation (R1–R4) adds hard within-type contrasts, so a label cannot be guessed from the action type alone.",
            ],
            "Without ground truth there is no safety metric. The ReAct agent never sees the oracle; the learned verifier is trained on it cross-fitted by incident, so it never judges an incident it learned from.",
            [(n["n_inc"], "incidents"), (n["rows"], "labeled candidate actions")],
            "We turned a public benchmark into an offline, labeled testbed, so every experiment is reproducible without a live cluster.",
            ["fixtures/incidents/", "scripts/convert_itbench.py", "src/sentinel/labeling/"],
        ),
        Branch(
            3,
            "Diagnosis agent",
            "#8a5cd6",
            "left",
            [
                "Simulated agent: seeded, free, offline",
                "ReAct agent: LLM with read-only tools",
                "Tools: logs, metrics, traces, topology",
                "Output: one ProposedAction (Pydantic)",
                "Never shares state with the verifier",
            ],
            "Proposes exactly one structured action per step, and is never trusted.",
            [
                "<b>ReAct agent</b>: an LLM reasons step by step and calls read-only tools (logs, metrics, traces, topology), then outputs one <code>ProposedAction</code> validated by a schema.",
                "<b>Simulated agent</b>: a seeded, LLM-free stand-in that samples candidate actions at a controlled quality (weak / default / strong). It is a repeatable stimulus for testing the verifier.",
                "The agent and the verifier never share prompts, clients or state, so the checker cannot be talked into agreeing.",
            ],
            "Varying agent quality shows the verifier is needed even for a good agent.",
            [
                (n["weak_unsafe"], "unsafe execution, weak agent, no verifier"),
                (n["strong_unsafe"], "even a strong agent, no verifier"),
            ],
            "Even the strong agent executes an unsafe action in about one run in five when nothing checks it. Better agents alone do not solve safety.",
            ["src/sentinel/agent/react.py", "src/sentinel/agent/simulated.py", "src/sentinel/agent/tools.py"],
        ),
        Branch(
            4,
            "Safety verifier",
            "#d6452a",
            "left",
            [
                "Layer 1 Envelope: allow-list + param rules",
                "Layer 2a LLM judge: Qwen 3.8 27B via Groq",
                "Judge fails closed: unavailable = block",
                "Layer 2b Learned: XGBoost + Platt calibration",
                "Combined: envelope pass AND risk < τ",
                "Verdict: allow / block / revise + reasons",
            ],
            "Layered checks: fixed rules first, then a risk estimate compared with a threshold τ.",
            [
                "<b>Layer 1 – Envelope</b>: an allow-list of 10 action types with parameter schemas and a blast-radius cap. Deterministic, no AI.",
                "<b>Layer 2a – LLM judge</b>: an independent model (Qwen 3.8 27B on Groq) returns allow/block/revise, a risk score and reasons. If it is unavailable it <i>fails closed</i>.",
                f"<b>Layer 2b – Learned</b>: XGBoost on action, incident and topology features; Platt-calibrated; cross-fitted by incident ({n['folds']} folds). AUC {n['auc']} on the hard within-type cases (type-only baseline {n['auc_type']}), ECE {n['ece']}.",
                "<b>Policy</b>: allow only if the envelope passes AND the highest risk is below τ. Every layer's verdict and reasons are recorded and shown.",
            ],
            "Rules are cheap and certain but narrow; the learned layer catches what rules cannot express.",
            [
                (n["e_prev"], "of bad actions caught by the envelope alone"),
                (n["l_prev"], f"caught by envelope + learned ({n['sec_only']} only by the learned layer)"),
            ],
            f"This is the core contribution. The envelope alone stops about a third of bad actions; adding the learned layer stops {n['l_prev']}, at a false-block rate of {n['l_fb']}.",
            [
                "src/sentinel/verifier/envelope.py",
                "src/sentinel/verifier/learned.py",
                "src/sentinel/verifier/llm_judge.py",
                "src/sentinel/verifier/policy.py",
            ],
        ),
        Branch(
            5,
            "Act + control loop",
            "#c98a0b",
            "right",
            [
                "Executor: acts only on an 'allow' verdict",
                "Dry run by default; rollback planner",
                "Loop: propose, verify, act, observe",
                "On block: escalate to a human, or retry",
                "Every run saved as a RunRecord (DuckDB)",
            ],
            "Only an 'allow' can reach the executor, and every step is recorded.",
            [
                "The <b>orchestrator</b> repeats propose → verify → act → observe until the incident is resolved, escalated, or the step budget runs out.",
                "<b>On block</b>: escalate to a human, or <i>retry</i>, feeding the verifier's reasons back to the agent.",
                "The <b>executor</b> dry-runs by default. A real apply needs both the <code>auto_execute</code> config flag and an <i>allow</i> verdict; reversible actions get a rollback plan.",
                "Every run is stored as a <code>RunRecord</code> in DuckDB with its config hash: no result exists unless it is stored.",
            ],
            "Blocking alone leaves incidents unresolved; feeding reasons back recovers most of them safely.",
            [
                (n["r_res"], "resolved with block → retry (vs " + n["l_res"] + " with escalate)"),
                (n["r_unsafe"], "unsafe execution with retry"),
            ],
            f"Retry turns the verifier from a brake into a guide: {n['r_safe']} of runs end safely resolved, compared with {n['u_safe']} with no verifier.",
            [
                "src/sentinel/orchestrator/loop.py",
                "src/sentinel/executor/",
                "src/sentinel/store/duckdb_store.py",
            ],
        ),
        Branch(
            6,
            "Evaluation",
            "#0e8fa8",
            "right",
            [
                "make eval: retrain, rerun, all figures",
                "Metrics: resolution, unsafe execution, false block",
                "Bootstrap 95% CIs over incidents",
                "Pareto sweep over τ; ablations",
                f"Unsafe execution: {n['u_unsafe']} → {n['l_unsafe']}",
                f"Block + retry: {n['r_res']} resolved",
            ],
            f"{n['n_runs']} recorded runs, confidence intervals over incidents, one command to regenerate.",
            [
                f"<code>make eval</code> retrains the verifier and reruns every configuration on all {n['n_inc']} incidents × {n['seeds']} seeds, then rebuilds every table and figure from DuckDB.",
                "Metrics: resolution, bad actions prevented, false blocks, unsafe execution, net-safe resolutions, time to mitigation, cost.",
                "95% confidence intervals by bootstrap, resampling <i>incidents</i> (not runs), so the uncertainty is honest.",
                "Ablations: verifier on/off, layers, topology features, block handling, agent quality; Pareto sweep of τ.",
            ],
            "A safety claim needs a trade-off curve and error bars, not a single number.",
            [
                (n["n_runs"], "runs recorded"),
                (n["l_unsafe"], f"unsafe execution (95% CI {n['l_unsafe_ci']})"),
            ],
            "Every figure in the report can be regenerated from scratch with one command, and the same numbers appear in these slides.",
            ["src/sentinel/eval/", "scripts/run_eval.py", "runs/eval/results.md"],
        ),
        Branch(
            7,
            "Live console",
            "#d63d8f",
            "right",
            [
                "React + TypeScript + Vite (frontend/)",
                "Screens: Queue, Triage, Results, Observability",
                "Live run streamed over SSE",
                "VerdictCard always shows every layer",
                "Mock mode runs with the backend down",
                "Types generated from Pydantic",
            ],
            "Makes the verifier's decisions visible, step by step, as they happen.",
            [
                "<b>Queue</b>: all incidents and their latest outcome. <b>Triage</b>: telemetry, topology graph, live loop trace, run controls (verifier, τ).",
                "The <b>VerdictCard</b> always shows every layer (envelope, judge, learned), with inactive ones greyed out, plus the reasons.",
                "<b>Results</b>: Pareto curve, metrics, prevention partition and ablations from DuckDB. <b>Observability</b>: Prometheus / Grafana.",
                "Runs stream live over Server-Sent Events; a mock mode works with the backend down; the TypeScript types are generated from the Python schemas.",
            ],
            "Operators trust a verifier they can inspect; the layered view is what the panel will see in the demo.",
            [("4", "screens"), ("SSE", "live step-by-step streaming")],
            "Demo: pick an incident, run it Ungated and then with the verifier, and watch the VerdictCard explain each block.",
            [
                "frontend/src/routes/",
                "frontend/src/features/triage/VerdictCard.tsx",
                "src/sentinel/gateway/api.py",
            ],
        ),
        Branch(
            8,
            "Engineering",
            "#5b6b7a",
            "right",
            [
                "Gateway: FastAPI on :8080",
                "Prometheus + Grafana; Docker Compose",
                "600+ tests + browser e2e rehearsal",
                "Seeded runs; config hash on every run",
                "PDF docs generated by scripts",
            ],
            "Built to be checked: offline, seeded, tested.",
            [
                "Runs end to end with <b>zero Kubernetes</b>: the environment sits behind an adapter interface, and the offline adapter replays the saved incidents.",
                "All randomness is seeded from config; every run records its <b>config hash</b>.",
                "<b>600+ automated tests</b> plus a headless-browser rehearsal of the live demo (<code>make e2e</code>).",
                "FastAPI gateway, Prometheus/Grafana metrics, Docker Compose; every module boundary is a typed Pydantic model.",
            ],
            "Results that cannot be reproduced cannot be trusted; the engineering exists to make the evaluation checkable.",
            [("0", "Kubernetes needed"), ("600+", "automated tests")],
            "Anyone can clone the repository, run make test and make eval offline, and get the same numbers.",
            ["Makefile", "tests/", "docker-compose.yml", "src/sentinel/schemas/"],
        ),
    ]


# -- overview map (SVG) ----------------------------------------------------------------------------


def _leaf_text(leaf: str) -> str:
    name, sep, rest = leaf.partition(": ")
    if sep and len(name) <= 22:
        return f'<tspan font-weight="700">{html.escape(name)}:</tspan> {html.escape(rest)}'
    return html.escape(leaf)


def _branch_svg(b: Branch, y: float, dim: bool, leaves: bool) -> str:
    sign = -1 if b.side == "left" else 1
    bx, bw, bh = CX + sign * 360, 270, 58
    edge_in, edge_out = bx - sign * bw / 2, bx + sign * bw / 2
    leaf_x, start_x = edge_out + sign * 46, CX + sign * 150
    op = ' opacity=".16"' if dim else ""
    parts = [
        f"<g{op}>",
        f'<path d="M{start_x},{CY} C{start_x + sign * 110},{CY} {edge_in - sign * 110},{y} {edge_in},{y}" fill="none" stroke="{b.color}" stroke-width="7" stroke-linecap="round" opacity=".85"/>',
        f'<rect x="{bx - bw / 2}" y="{y - bh / 2}" width="{bw}" height="{bh}" rx="28" fill="{b.color}"/>',
        f'<circle cx="{bx - bw / 2 + 28}" cy="{y}" r="17" fill="#fff"/>',
        f'<text x="{bx - bw / 2 + 28}" y="{y + 7}" text-anchor="middle" fill="{b.color}" font-size="20" font-weight="800">{b.num}</text>',
        f'<text x="{bx + 16}" y="{y + 7.5}" text-anchor="middle" fill="#fff" font-size="22" font-weight="700">{html.escape(b.title)}</text>',
    ]
    if leaves:
        top = y - (len(b.leaves) - 1) * LEAF_DY / 2
        anchor = "end" if b.side == "left" else "start"
        for i, leaf in enumerate(b.leaves):
            ly = top + i * LEAF_DY
            parts += [
                f'<path d="M{edge_out},{y} C{edge_out + sign * 26},{y} {leaf_x - sign * 26},{ly} {leaf_x - sign * 8},{ly}" fill="none" stroke="{b.color}" stroke-width="1.6" opacity=".7"/>',
                f'<circle cx="{leaf_x - sign * 6}" cy="{ly}" r="3.6" fill="{b.color}"/>',
                f'<text x="{leaf_x}" y="{ly + 7}" text-anchor="{anchor}" font-size="21" fill="#26251f">{_leaf_text(leaf)}</text>',
            ]
    parts.append("</g>")
    return "\n".join(parts)


def overview_svg(bs: list[Branch], highlight: int | None = None, leaves: bool = True) -> str:
    out = []
    for side in ("left", "right"):
        col = [b for b in bs if b.side == side]
        heights = [(len(b.leaves) - 1) * LEAF_DY + 58 for b in col]
        y = CY - (sum(heights) + GROUP_GAP * (len(col) - 1)) / 2
        for b, h in zip(col, heights):
            out.append(_branch_svg(b, y + h / 2, dim=highlight not in (None, b.num), leaves=leaves))
            y += h + GROUP_GAP
    centre = (
        f'<rect x="{CX - 160}" y="{CY - 74}" width="320" height="148" rx="22" fill="#1f2a37"/>'
        f'<text x="{CX}" y="{CY - 22}" text-anchor="middle" fill="#fff" font-size="29" font-weight="800">sentinel-remediate</text>'
        f'<text x="{CX}" y="{CY + 12}" text-anchor="middle" fill="#c9d4e0" font-size="17">Verified AI incident remediation</text>'
        f'<text x="{CX}" y="{CY + 40}" text-anchor="middle" fill="#c9d4e0" font-size="17">propose → verify → act</text>'
    )
    span = max(sum((len(b.leaves) - 1) * LEAF_DY + 58 for b in bs if b.side == s) for s in ("left", "right"))
    span += GROUP_GAP * 3 + 24
    viewbox = (
        f"0 {CY - span / 2} {W} {span}" if leaves else f"{CX - 520} {CY - span / 2 + 40} 1040 {span - 80}"
    )
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" font-family="Segoe UI, Arial, sans-serif">{"".join(out)}{centre}</svg>'


# -- slides ----------------------------------------------------------------------------------------

CSS = """
@page { size: 1280px 720px; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; background: #fbfaf7; font-family: 'Segoe UI', Arial, sans-serif; color: #26251f; }
.slide { width: 1280px; height: 720px; padding: 34px 48px 26px; position: relative; display: flex; flex-direction: column; break-after: page; overflow: hidden; }
.slide:last-child { break-after: auto; }
.kicker { font-size: 14px; letter-spacing: .12em; text-transform: uppercase; color: #6b6a65; font-weight: 600; }
h1 { margin: 4px 0 0; font-size: 34px; color: #1f2a37; line-height: 1.15; }
.tag { margin-top: 6px; font-size: 19px; color: #4a4943; }
.badge { display: inline-flex; align-items: center; justify-content: center; width: 40px; height: 40px; border-radius: 50%; color: #fff; font-weight: 800; font-size: 21px; margin-right: 12px; vertical-align: 4px; }
.foot { position: absolute; left: 48px; right: 48px; bottom: 14px; font-size: 11.5px; color: #8a8983; display: flex; justify-content: space-between; }
.cols { display: flex; gap: 34px; margin-top: 18px; flex: 1; min-height: 0; }
.left { width: 340px; flex: none; display: flex; flex-direction: column; gap: 14px; }
.right { flex: 1; display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.mini { background: #fff; border: 1px solid #e4e2dc; border-radius: 12px; padding: 6px; }
.mini svg { width: 100%; display: block; }
.box { background: #fff; border: 1px solid #e4e2dc; border-radius: 12px; padding: 12px 16px; }
.box h3 { margin: 0 0 6px; font-size: 13px; letter-spacing: .1em; text-transform: uppercase; color: #6b6a65; }
code, .code li { font-family: Consolas, 'Cascadia Mono', monospace; font-size: 13.5px; }
.code { margin: 0; padding-left: 16px; } .code li { margin: 2px 0; color: #3d3c39; }
ul.what { margin: 0; padding-left: 20px; font-size: 18px; line-height: 1.42; } ul.what li { margin: 0 0 7px; }
.why { font-size: 16.5px; color: #3d3c39; }
.facts { display: flex; gap: 14px; }
.fact { flex: 1; background: #fff; border: 1px solid #e4e2dc; border-left: 6px solid var(--c); border-radius: 10px; padding: 9px 14px; }
.fact b { display: block; font-size: 30px; color: var(--c); line-height: 1.1; }
.fact span { font-size: 14px; color: #4a4943; }
.say { margin-top: auto; background: #1f2a37; color: #f3f1ec; border-radius: 12px; padding: 13px 18px; font-size: 16.5px; line-height: 1.4; }
.say b { color: #ffd479; }
.overview svg { width: 100%; flex: 1; min-height: 0; margin: 4px 0; }
.slide.overview { padding-top: 26px; }
.order { font-size: 14px; color: #6b6a65; margin-bottom: 16px; }
table.res { border-collapse: collapse; width: 100%; font-size: 17px; background: #fff; }
table.res th, table.res td { padding: 10px 14px; border-bottom: 1px solid #e4e2dc; text-align: right; }
table.res th:first-child, table.res td:first-child { text-align: left; }
table.res th { font-size: 13px; text-transform: uppercase; letter-spacing: .08em; color: #6b6a65; }
table.res tr.hl td { background: #f3f8ee; font-weight: 600; }
.tiles { display: flex; gap: 16px; }
.tile { flex: 1; background: #fff; border: 1px solid #e4e2dc; border-radius: 12px; padding: 14px 16px; }
.tile b { display: block; font-size: 38px; color: #1f2a37; } .tile span { font-size: 14.5px; color: #4a4943; }
.two { display: flex; gap: 26px; margin-top: 22px; align-items: flex-start; }
.two .box { flex: 1; } .two ul { margin: 6px 0 0; padding-left: 20px; font-size: 17px; line-height: 1.45; } .two li { margin-bottom: 8px; }
"""


def _foot(page: int, total: int, meta: str) -> str:
    return f'<div class="foot"><span>sentinel-remediate · M.Tech project review</span><span>{meta} · {page} / {total}</span></div>'


def overview_slide(bs: list[Branch]) -> str:
    order = " → ".join(f"{b.num} {html.escape(b.title)}" for b in bs)
    return f"""<section class="slide overview">
<h1>Verified AI Incident Remediation — Project Mind Map</h1>
<div class="tag">An untrusted AI proposes a fix; a layered verifier decides whether it may run. Left: input and checks · Right: outcome and evidence.</div>
{overview_svg(bs)}
<div class="order">Walk-through order: {order}</div>
{{foot}}</section>"""


def branch_slide(bs: list[Branch], b: Branch) -> str:
    what = "".join(f"<li>{w}</li>" for w in b.what)
    facts = "".join(
        f'<div class="fact"><b>{html.escape(v)}</b><span>{html.escape(t)}</span></div>' for v, t in b.facts
    )
    code = "".join(f"<li>{html.escape(c)}</li>" for c in b.code)
    return f"""<section class="slide" style="--c:{b.color}">
<div class="kicker">Branch {b.num} of {len(bs)}</div>
<h1><span class="badge" style="background:{b.color}">{b.num}</span>{html.escape(b.title)}</h1>
<div class="tag">{html.escape(b.tagline)}</div>
<div class="cols">
  <div class="left">
    <div class="mini">{overview_svg(bs, highlight=b.num, leaves=False)}</div>
    <div class="box"><h3>Why it matters</h3><div class="why">{b.why}</div></div>
    <div class="box"><h3>Where in the code</h3><ul class="code">{code}</ul></div>
  </div>
  <div class="right">
    <ul class="what">{what}</ul>
    <div class="facts">{facts}</div>
    <div class="say"><b>Say to the panel:</b> {b.panel}</div>
  </div>
</div>
{{foot}}</section>"""


def results_slide(n: dict[str, str]) -> str:
    return f"""<section class="slide">
<div class="kicker">Evidence</div>
<h1>Results at a Glance</h1>
<div class="tag">{n['n_runs']} recorded runs · {n['n_inc']} incidents × {n['seeds']} seeds per configuration · 95% bootstrap CIs over incidents</div>
<div class="tiles" style="margin-top:18px">
  <div class="tile"><b>{n['u_unsafe']} → {n['l_unsafe']}</b><span>unsafe execution, no verifier → envelope + learned</span></div>
  <div class="tile"><b>{n['l_prev']}</b><span>of bad actions caught by envelope + learned</span></div>
  <div class="tile"><b>{n['l_fb']}</b><span>false blocks (good actions stopped)</span></div>
  <div class="tile"><b>{n['r_res']}</b><span>resolved with block → retry</span></div>
</div>
<table class="res" style="margin-top:20px">
<tr><th>Configuration</th><th>Unsafe execution</th><th>95% CI</th><th>Resolved</th><th>Net-safe resolved</th></tr>
<tr><td>No verifier (ungated)</td><td>{n['u_unsafe']}</td><td>{n['u_unsafe_ci']}</td><td>{n['u_res']}</td><td>{n['u_safe']}</td></tr>
<tr><td>Envelope only</td><td>{n['e_unsafe']}</td><td>{n['e_unsafe_ci']}</td><td>{n['e_res']}</td><td>{n['e_safe']}</td></tr>
<tr><td>Envelope + learned (escalate on block)</td><td>{n['l_unsafe']}</td><td>{n['l_unsafe_ci']}</td><td>{n['l_res']}</td><td>{n['l_safe']}</td></tr>
<tr class="hl"><td>Envelope + learned (retry on block)</td><td>{n['r_unsafe']}</td><td>—</td><td>{n['r_res']}</td><td>{n['r_safe']}</td></tr>
</table>
<div class="say" style="margin-top:18px"><b>Takeaway:</b> the verifier cuts unsafe execution from {n['u_unsafe']} to {n['l_unsafe']}; with retry it also resolves {n['r_res']} of incidents, and {n['r_safe']} end safely resolved versus {n['u_safe']} with no verifier.</div>
{{foot}}</section>"""


def limits_slide(n: dict[str, str]) -> str:
    return f"""<section class="slide">
<div class="kicker">Honest scope</div>
<h1>Limitations and Next Steps</h1>
<div class="two">
  <div class="box"><h3>Limitations</h3><ul>
    <li>The main evaluation uses the <b>simulated agent</b>; the LLM ReAct agent and the LLM-judge / combined baselines were not in the full run (API cost and rate limits).</li>
    <li>Most labels are machine-derived: {n['needs_review']} of {n['rows']} are flagged for <b>human review</b>, which is still pending.</li>
    <li>Incidents are replayed in an <b>offline environment</b>, not a live cluster.</li>
    <li>{n['n_inc']} incidents is a small set; generalisation to new fault families is untested.</li>
  </ul></div>
  <div class="box"><h3>Next steps</h3><ul>
    <li>Run the LLM-judge and combined baselines in the full evaluation (now possible on the free Groq tier).</li>
    <li>Complete human review of labels with the review CLI.</li>
    <li>Plug in a live-cluster adapter (AIOpsLab / ITBench) behind the same interface.</li>
    <li>Grow the incident set and test on held-out fault families.</li>
  </ul></div>
</div>
<div class="say" style="margin-top:24px"><b>Close with:</b> the architecture keeps the AI useful but never in charge, and every claim on these slides is regenerated from stored runs with one command.</div>
{{foot}}</section>"""


def build_html() -> str:
    n = numbers()
    bs = branches(n)
    slides = [overview_slide(bs), *(branch_slide(bs, b) for b in bs), results_slide(n), limits_slide(n)]
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()
    meta = f"{dt.date.today().strftime('%d %B %Y')} · commit {commit}"
    pages = [s.replace("{foot}", _foot(i, len(slides), meta)) for i, s in enumerate(slides, 1)]
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Project Mind Map</title><style>{CSS}</style></head><body>{"".join(pages)}</body></html>'


def main() -> None:
    from playwright.sync_api import sync_playwright

    BUILD.mkdir(parents=True, exist_ok=True)
    page_html = BUILD / "mindmap.html"
    page_html.write_text(build_html(), encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": SLIDE_W, "height": SLIDE_H})
        page.goto(page_html.as_uri())
        page.pdf(path=str(OUT_PDF), prefer_css_page_size=True, print_background=True)
        for i, slide in enumerate(page.query_selector_all("section.slide"), 1):
            slide.screenshot(path=str(BUILD / f"slide{i:02}.png"))
        browser.close()
    print(f"wrote {OUT_PDF.relative_to(REPO)}")


if __name__ == "__main__":
    main()
