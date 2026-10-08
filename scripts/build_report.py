#!/usr/bin/env python
"""`make report-pdf` -- builds docs/architecture_report.pdf from docs/report/{front,body}.html.

Every number and results table is filled in from the evaluation outputs (runs/eval/results.json,
the learned-verifier metrics, the configs, the fixtures), never typed by hand, so re-running
`make eval` and then this script keeps the report in step with the code. Pages are rendered by
headless Chromium (Playwright); the table of contents gets real page numbers from a first render
pass (pypdf text search), then front matter (unnumbered) and body (numbered) are merged.

Needs: make eval (results + figures) and make e2e (console screenshots) to have been run, plus
`pip install playwright pypdf && python -m playwright install chromium`.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from sentinel.env.offline_adapter import OfflineEnvAdapter  # noqa: E402
from sentinel.labeling.dataset import build_dataset  # noqa: E402

SRC = REPO / "docs" / "report"
BUILD = SRC / "build"
OUT = REPO / "docs" / "architecture_report.pdf"
RESULTS = REPO / "runs" / "eval" / "results.json"
FIGS = REPO / "runs" / "eval" / "figures"
SHOTS = REPO / "runs" / "e2e"
FRONTEND_SKIP = ("types.ts", "vite-env")


# -- formatting ------------------------------------------------------------------------------------


def pct(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{100 * x:.{digits}f}%"


def ci(pair) -> str:
    return "" if not pair else f'<br><span class="muted">[{100 * pair[0]:.1f}, {100 * pair[1]:.1f}]</span>'


def esc(text) -> str:
    return html.escape(str(text))


def table(
    caption: str,
    headers: list[str],
    rows: list[list[str]],
    num_cols: set[int] = frozenset(),
    highlight: set[int] = frozenset(),
) -> str:
    head = "".join(f'<th class="{"num" if i in num_cols else ""}">{h}</th>' for i, h in enumerate(headers))
    body = []
    for r, row in enumerate(rows):
        cells = "".join(f'<td class="{"num" if i in num_cols else ""}">{c}</td>' for i, c in enumerate(row))
        body.append(f'<tr class="{"highlight" if r in highlight else ""}">{cells}</tr>')
    return f"<table><caption>{caption}</caption><tr>{head}</tr>{''.join(body)}</table>"


# -- facts ----------------------------------------------------------------------------------------


def count_tests() -> int:
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=REPO, capture_output=True, text=True
    ).stdout
    match = re.search(r"(\d+) tests? collected", out)
    return int(match.group(1)) if match else 0


def count_lines(root: Path, patterns: tuple[str, ...], exclude: tuple[str, ...] = ()) -> int:
    total = 0
    for pattern in patterns:
        for path in root.rglob(pattern):
            if not any(part in str(path) for part in exclude):
                total += len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
    return total


def git_commit() -> str:
    out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True)
    return out.stdout.strip() or "unknown"


def ablation(results: dict, name: str) -> dict[tuple[str, str], float]:
    return {(a["variant"], a["metric"]): a["value"] for a in results["ablations"] if a["name"] == name}


# -- generated tables ----------------------------------------------------------------------------


def envelope_table() -> str:
    spec = yaml.safe_load((REPO / "config" / "action_envelope.yaml").read_text(encoding="utf-8"))
    rows = []
    for name, a in spec["allowed_actions"].items():
        params = []
        for p, rule in a.get("params", {}).items():
            extra = []
            if "min" in rule or "max" in rule:
                extra.append(f"{rule.get('min', '')}–{rule.get('max', '')}")
            if "enum" in rule:
                extra.append(f"{len(rule['enum'])} kinds")
            star = "" if rule.get("required") else "?"
            params.append(f"<code>{p}{star}</code>" + (f" ({', '.join(extra)})" if extra else ""))
        rows.append(
            [
                f"<code>{name}</code>",
                a.get("scope", ""),
                a.get("blast_radius", ""),
                "yes" if a.get("reversible") else "no",
                ", ".join(params),
            ]
        )
    pol = spec["policy"]
    caption = (
        "<b>Table 5.</b> The action envelope (<code>config/action_envelope.yaml</code>). "
        f"Policy: blast radius ≤ "
        f"<i>{pol['max_allowed_blast_radius']}</i>; forbidden namespaces: "
        f"{', '.join(pol['forbidden_namespaces'])}. <code>?</code> marks an optional parameter."
    )
    return table(caption, ["Action type", "Scope", "Blast radius", "Reversible", "Parameters"], rows)


def _family_cells(item: tuple[str, Counter] | None) -> list[str]:
    if item is None:
        return ["", "", ""]
    family, sources = item
    return [
        f"<code>{family}</code>",
        str(sum(sources.values())),
        ", ".join(f"{k} {v}" for k, v in sorted(sources.items())),
    ]


def family_table(env: OfflineEnvAdapter) -> tuple[str, int]:
    by_family: dict[str, Counter] = defaultdict(Counter)
    for incident_id in env.list_incidents():
        inc = env.get_incident(incident_id)
        by_family[inc.fault_family or "unknown"]["ITBench" if inc.source == "itbench" else "hand-built"] += 1
    items = sorted(by_family.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))
    half = (len(items) + 1) // 2
    rows = []
    for i in range(half):
        right = items[i + half] if i + half < len(items) else None
        rows.append(_family_cells(items[i]) + _family_cells(right))
    n_inc = len(env.list_incidents())
    caption = f"<b>Table 8.</b> Incidents by fault family ({n_inc} incidents, {len(items)} families)."
    return table(caption, ["Fault family", "n", "Source", "Fault family", "n", "Source"], rows, {1, 4}), len(
        items
    )


def dataset_table(env: OfflineEnvAdapter) -> tuple[str, int, int]:
    rows_ = build_dataset(env)
    cross: dict[str, Counter] = defaultdict(Counter)
    for r in rows_:
        cross[r.provenance][r.label] += 1
    labels = ["correct", "ineffective", "destructive", "out_of_envelope"]
    meaning = {
        "hand_built": "the 6 hand-built incidents",
        "itbench_derived": "mapped from ITBench recommended actions",
        "converter_synthesized": "generated by converter rules",
        "rule_augmented": "hard-case rules (§7.4)",
        "human_reviewed": "confirmed by a reviewer",
    }
    rows = []
    for prov in [
        "hand_built",
        "itbench_derived",
        "converter_synthesized",
        "rule_augmented",
        "human_reviewed",
    ]:
        if prov in cross:
            c = cross[prov]
            rows.append(
                [
                    f"<code>{prov}</code>",
                    meaning[prov],
                    *[str(c[label]) for label in labels],
                    str(sum(c.values())),
                ]
            )
    totals = Counter(r.label for r in rows_)
    rows.append(
        ["<b>Total</b>", "", *[f"<b>{totals[label]}</b>" for label in labels], f"<b>{len(rows_)}</b>"]
    )
    caption = (
        "<b>Table 9.</b> Labeled candidate actions by provenance and label. Every converted and rule-derived "
        "label carries <code>needs_review</code> until confirmed with the review CLI."
    )
    scored = sum(1 for r in rows_ if r.label != "out_of_envelope")
    return (
        table(
            caption,
            ["Provenance", "Origin", "correct", "ineffective", "destructive", "out-of-env.", "total"],
            rows,
            {2, 3, 4, 5, 6},
        ),
        len(rows_),
        scored,
    )


def baselines_table(results: dict) -> str:
    rows = []
    for b in results["baselines"]:
        rows.append(
            [
                b["baseline"],
                pct(b["resolution"]) + ci(b["resolution_ci95"]),
                pct(b["bad_action_prevented"]) + ci(b["bad_action_prevented_ci95"]),
                pct(b["false_block"]) + ci(b["false_block_ci95"]),
                pct(b["unsafe_execution"]) + ci(b["unsafe_execution_ci95"]),
                pct(b["net_safe_resolutions"]) + ci(b["net_safe_resolutions_ci95"]),
                f"{b['steps_to_mitigation']:.2f}" if b["steps_to_mitigation"] else "n/a",
                str(b["n_runs"]),
            ]
        )
    best = len(rows) - 1
    caption = (
        "<b>Table 12.</b> Baselines at τ = 0.5 (escalate on block), every incident × every seed. "
        "Brackets: 95% "
        "bootstrap CI over incidents. Steps: mean loop steps to resolution."
    )
    return table(
        caption,
        [
            "Baseline",
            "Resolution",
            "Bad-action prevented",
            "False block",
            "Unsafe execution",
            "Net-safe resolution",
            "Steps",
            "Runs",
        ],
        rows,
        {1, 2, 3, 4, 5, 6, 7},
        {best},
    )


def partition_table(results: dict) -> str:
    rows = [
        [p["baseline"], pct(p["caught_by_envelope"]), pct(p["caught_by_secondary_only"]), pct(p["missed"])]
        for p in results["prevention_partition"]
    ]
    caption = (
        "<b>Table 13.</b> Prevention partition: shares of destructive proposals by the layer "
        "that stopped them."
    )
    return table(
        caption, ["Baseline", "Caught by envelope", "Caught by secondary only", "Missed"], rows, {1, 2, 3}
    )


def block_table(results: dict) -> str:
    a = ablation(results, "Block handling")
    variants = sorted({v for v, _ in a}, key=lambda v: (("learned" in v), "retry" in v))
    rows = [
        [
            v,
            pct(a[(v, "resolution")]),
            pct(a[(v, "unsafe_execution")]),
            pct(a[(v, "net_safe_resolutions")]),
            f"{a[(v, 'steps_to_mitigation')]:.2f}",
        ]
        for v in variants
    ]
    caption = (
        "<b>Table 14.</b> What a block means: escalate to a human (blueprint default) versus retry "
        "with the block "
        "reasons as feedback (τ = 0.5)."
    )
    return table(
        caption,
        ["Variant: on block", "Resolution", "Unsafe execution", "Net-safe resolution", "Steps"],
        rows,
        {1, 2, 3, 4},
        {len(rows) - 1},
    )


def classifier_table(training: dict) -> str:
    lv, nt, tb = (
        training["learned_verifier"],
        training["learned_verifier_no_topology"],
        training["type_only_baseline"],
    )

    def row(name, m):
        return [
            name,
            str(m["n"]),
            str(m["positives"]),
            f"{m['auc']:.3f}",
            f"{m['ece']:.3f}",
            f"{m['brier']:.3f}",
        ]

    rows = [
        row("Type-only baseline", tb),
        row("Learned verifier", lv["all"]),
        row("Learned, no topology", nt["all"]),
        row("<i>Within-type subset:</i> type-only", lv["within_type_contrast_type_only_baseline"]),
        row("<i>Within-type subset:</i> learned", lv["within_type_contrast"]),
        row("<i>Within-type subset:</i> learned, no topology", nt["within_type_contrast"]),
        row("Learned · hand-built incidents only", lv["p0_incidents"]),
        row("Learned · ITBench incidents only", lv["itbench_incidents"]),
    ]
    types = ", ".join(f"<code>{t}</code>" for t in lv["within_type_contrast_types"])
    caption = (
        "<b>Table 15.</b> Out-of-fold classification of destructive actions (incident-level 5-fold "
        f"cross-fitting). Within-type subset: action types occurring with both labels ({types})."
    )
    return table(
        caption, ["Model / subset", "n", "destructive", "AUC", "ECE", "Brier"], rows, {1, 2, 3, 4, 5}, {4}
    )


def agent_quality_table(results: dict, mixes: dict) -> str:
    a = ablation(results, "Agent quality")
    names = {"none": "Ungated", "envelope": "Envelope only", "learned": "Envelope + learned"}
    rows = []
    for mix in ("strong", "default", "weak"):
        if (f"none@{mix}", "unsafe_execution") not in a:
            continue
        m = mixes[mix]
        for variant in ("none", "envelope", "learned"):
            key = f"{variant}@{mix}"
            rows.append(
                [
                    f"{mix} ({pct(m['destructive'], 0)} destructive)" if variant == "none" else "",
                    names[variant],
                    pct(a[(key, "unsafe_execution")]),
                    pct(a[(key, "resolution")]),
                    pct(a[(key, "net_safe_resolutions")]),
                ]
            )
    caption = (
        "<b>Table 16.</b> Agent-quality ablation: simulated planners proposing progressively "
        "more destructive actions."
    )
    return table(
        caption,
        ["Planner", "Verification", "Unsafe execution", "Resolution", "Net-safe resolution"],
        rows,
        {2, 3, 4},
    )


def topology_table(results: dict) -> tuple[str, str, str]:
    a = ablation(results, "Topology features (learned)")
    rows = [
        [v, pct(a[(v, "bad_action_prevented")]), pct(a[(v, "false_block")])]
        for v in ("with topology", "without topology")
    ]
    d_prev = a[("without topology", "bad_action_prevented")] - a[("with topology", "bad_action_prevented")]
    d_fb = a[("without topology", "false_block")] - a[("with topology", "false_block")]
    caption = "<b>Table 17.</b> Learned verifier with and without topology features (τ = 0.5, end to end)."
    return (
        table(caption, ["Learned verifier", "Bad-action prevented", "False block"], rows, {1, 2}),
        f"{100 * d_prev:+.1f} pp",
        f"{100 * d_fb:+.1f} pp",
    )


def config_rows(cfg: dict) -> str:
    entries = [
        ("agent.kind", "simulated LLM-free planner (offline) or ReAct LLM agent"),
        ("agent.simulated.label_mix", "proposal mix of the simulated planner"),
        ("models.diagnosis_agent", "LLM for the ReAct agent"),
        ("models.llm_judge", "LLM for the judge"),
        ("budgets.max_steps", "orchestrator step cap per run"),
        ("budgets.context_tokens", "telemetry compaction target"),
        ("verifier.active", "variant: none · envelope · llm_judge · learned · combined"),
        ("verifier.threshold", "τ, the risk cutoff"),
        ("execution.auto_execute", "real execution opt-in (safety rule)"),
        ("execution.dry_run", "dry-run by default"),
        ("orchestrator.on_block", "escalate (default) or retry"),
        ("orchestrator.seed", "base seed"),
        ("eval.seeds", "evaluation seeds"),
        ("eval.bootstrap_resamples", "CI resamples"),
        ("gateway.step_delay_ms", "console display pacing only"),
        ("store.path", "DuckDB run store"),
    ]
    out = []
    for key, meaning in entries:
        value = cfg
        for part in key.split("."):
            value = value[part]
        text = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        out.append(f"<tr><td><code>{key}</code></td><td class='mono'>{esc(text)}</td><td>{meaning}</td></tr>")
    return "\n".join(out)


LAYOUT = """sentinel-remediate/
├── config/              runtime, envelope, labeling-rule, ITBench-mapping,
│                        Prometheus and Grafana configuration
├── fixtures/incidents/  41 incident fixtures (6 hand-built + 35 ITBench)
├── src/sentinel/
│   ├── schemas/         Pydantic contracts
│   ├── env/             EnvAdapter ABC + OfflineEnvAdapter (+ cluster stubs)
│   ├── context/         context builder, retrievers
│   ├── agent/           ReAct agent, simulated planner, tools, factory
│   ├── verifier/        envelope, llm_judge, learned, features, policy
│   ├── executor/        executor, rollback (plans only)
│   ├── orchestrator/    loop, factory
│   ├── labeling/        taxonomy, oracle labeler, hard cases, review CLI
│   ├── store/           DuckDB run store
│   ├── eval/            metrics, runner, pareto, ablations, report, figures
│   ├── gateway/         FastAPI app, console API (SSE), runs, LLM clients
│   ├── observability/   Prometheus metrics
│   └── config.py        load_config, config_hash
├── frontend/            React console (generated types, mock + live mode)
├── scripts/             ITBench fetch/convert, demos, training, evaluation,
│                        browser rehearsal, this report's build
├── tests/               one module per component; no network or API key
├── notebooks/           analysis.ipynb (reads the same report code)
└── docs/                this report, ITBench converter specification"""


# -- assembly -------------------------------------------------------------------------------------


def values() -> dict[str, str]:
    if not RESULTS.exists():
        sys.exit(f"{RESULTS} not found -- run `make eval` first")
    r = json.loads(RESULTS.read_text(encoding="utf-8"))
    training = r["learned_verifier_training"]
    cfg = yaml.safe_load((REPO / "config" / "default.yaml").read_text(encoding="utf-8"))
    meta = yaml.safe_load((SRC / "report_meta.yaml").read_text(encoding="utf-8"))
    env = OfflineEnvAdapter()
    b = {x["variant"]: x for x in r["baselines"]}
    part = {p["variant"]: p for p in r["prevention_partition"]}
    block = ablation(r, "Block handling")
    lv = training["learned_verifier"]
    nt = training["learned_verifier_no_topology"]
    learned_pts = [p for p in r["pareto"].get("learned", []) if p["bad_action_prevented"] is not None]
    fam_html, n_families = family_table(env)
    ds_html, ds_rows, ds_scored = dataset_table(env)
    topo_html, d_prev, d_fb = topology_table(r)
    images = {
        "img_pareto": FIGS / "pareto.png",
        "img_partition": FIGS / "prevention_partition.png",
        "img_reliability": FIGS / "reliability.png",
        "img_agent_quality": FIGS / "agent_quality.png",
        "img_shot_thesis": SHOTS / "3_thesis_blocked.png",
        "img_shot_results": SHOTS / "5_results.png",
    }
    missing = [str(p) for p in images.values() if not p.exists()]
    if missing:
        sys.exit("missing images (run `make eval` and `make e2e`):\n  " + "\n  ".join(missing))
    v = {k: esc(val) for k, val in meta.items()}
    v.update({k: p.as_uri() for k, p in images.items()})
    v.update(
        {
            "date": date.today().strftime("%d %B %Y"),
            "commit": git_commit(),
            "n_runs": f"{r['n_runs']:,}",
            "n_incidents": str(len(env.list_incidents())),
            "n_families": str(n_families),
            "n_seeds": str(len(cfg["eval"]["seeds"])),
            "n_cells": str(r["n_runs"] // (len(env.list_incidents()) * len(cfg["eval"]["seeds"]))),
            "tau_grid": "{" + ", ".join(f"{t:g}" for t in cfg["eval"]["tau_grid"]) + "}",
            "bootstrap": str(cfg["eval"]["bootstrap_resamples"]),
            "n_tests": str(count_tests()),
            "loc_src": f"{count_lines(REPO / 'src' / 'sentinel', ('*.py',)):,}",
            "loc_tests": f"{count_lines(REPO / 'tests', ('*.py',)):,}",
            "loc_frontend": f"{count_lines(REPO / 'frontend' / 'src', ('*.ts', '*.tsx'), FRONTEND_SKIP):,}",
            "unsafe_none": pct(b["none"]["unsafe_execution"]),
            "unsafe_env": pct(b["envelope"]["unsafe_execution"]),
            "unsafe_learned": pct(b["learned"]["unsafe_execution"]),
            "prev_env": pct(b["envelope"]["bad_action_prevented"]),
            "prev_learned": pct(b["learned"]["bad_action_prevented"]),
            "fb_learned": pct(b["learned"]["false_block"]),
            "netsafe_none": pct(b["none"]["net_safe_resolutions"]),
            "res_learned_retry": pct(block[("Envelope + learned: retry", "resolution")]),
            "unsafe_learned_retry": pct(block[("Envelope + learned: retry", "unsafe_execution")]),
            "netsafe_learned_retry": pct(block[("Envelope + learned: retry", "net_safe_resolutions")]),
            "missed_env": pct(part["envelope"]["missed"]),
            "missed_learned": pct(part["learned"]["missed"]),
            "secondary_learned": pct(part["learned"]["caught_by_secondary_only"]),
            # of the destructive proposals the envelope PASSES, the share the learned layer stops
            "residue_caught": pct(
                part["learned"]["caught_by_secondary_only"]
                / (part["learned"]["caught_by_secondary_only"] + part["learned"]["missed"])
            ),
            "auc_all": f"{lv['all']['auc']:.3f}",
            "ece_all": f"{lv['all']['ece']:.3f}",
            "auc_type": f"{training['type_only_baseline']['auc']:.3f}",
            "auc_within": f"{lv['within_type_contrast']['auc']:.3f}",
            "auc_within_type": f"{lv['within_type_contrast_type_only_baseline']['auc']:.3f}",
            "brier_within": f"{lv['within_type_contrast']['brier']:.3f}",
            "brier_within_type": f"{lv['within_type_contrast_type_only_baseline']['brier']:.3f}",
            "auc_p0": f"{lv['p0_incidents']['auc']:.3f}",
            "auc_within_notopo": f"{nt['within_type_contrast']['auc']:.3f}",
            "pareto_prev_range": f"{pct(min(p['bad_action_prevented'] for p in learned_pts))} and "
            f"{pct(max(p['bad_action_prevented'] for p in learned_pts))}",
            "pareto_fb_range": f"{pct(min(p['false_block'] for p in learned_pts))}–"
            f"{pct(max(p['false_block'] for p in learned_pts))}",
            "topo_prev_delta": d_prev,
            "topo_fb_delta": d_fb,
            "ds_rows": str(ds_rows),
            "ds_scored": str(ds_scored),
            "envelope_table": envelope_table(),
            "family_table": fam_html,
            "dataset_table": ds_html,
            "baselines_table": baselines_table(r),
            "partition_table": partition_table(r),
            "block_table": block_table(r),
            "classifier_table": classifier_table(training),
            "agent_quality_table": agent_quality_table(r, cfg["eval"]["agent_mixes"]),
            "topology_table": topo_html,
            "skipped_list": "<ul>"
            + "".join(
                f"<li><b>{esc(s['cell'])} / {esc(s['name'])}</b> — {esc(s['reason'])}</li>"
                for s in r["skipped"]
            )
            + "</ul>",
            "config_rows": config_rows(cfg),
            "layout": esc(LAYOUT),
        }
    )
    return v


def fill(template: str, v: dict[str, str]) -> str:
    out = re.sub(r"\{\{(\w+)\}\}", lambda m: v[m.group(1)] if m.group(1) in v else m.group(0), template)
    left = sorted(set(re.findall(r"\{\{(\w+)\}\}", out)))
    if left:
        sys.exit(f"unfilled placeholders: {left}")
    return out


def entries(body_html: str) -> list[tuple[str, str, str]]:
    """(level, number, title) for h1/h2 headings, figures and tables, in document order."""
    found = []
    pattern = (
        r'<h([12])[^>]*><span class="num">([^<]+)</span>(.*?)</h\1>'
        r"|<(?:figcaption|caption)><b>((?:Figure|Table) \d+)\.</b>(.*?)(?:</figcaption>|</caption>)"
    )
    for m in re.finditer(pattern, body_html, re.S):
        if m.group(1):
            found.append((f"l{m.group(1)}", m.group(2), re.sub(r"<[^>]+>", "", m.group(3)).strip()))
        else:
            first = re.split(r"(?<=[.])\s", re.sub(r"<[^>]+>", "", m.group(5)).strip())[0]
            found.append(("fig" if m.group(4).startswith("Figure") else "tab", m.group(4), first.rstrip(".")))
    return found


def render(page, html_path: Path, pdf_path: Path, *, numbered: bool, title: str) -> None:
    page.goto(html_path.as_uri())
    page.wait_for_load_state("networkidle")
    options = {"path": str(pdf_path), "prefer_css_page_size": True, "print_background": True}
    if numbered:
        style = (
            "font-family:Segoe UI,Arial,sans-serif;font-size:7.5px;color:#6b6a65;"
            "width:100%;padding:0 20mm 0 22mm;"
        )
        options.update(
            {
                "display_header_footer": True,
                "header_template": f'<div style="{style}display:flex;justify-content:space-between">'
                f"<span>{esc(title)}</span><span>sentinel-remediate</span></div>",
                "footer_template": f'<div style="{style}text-align:center">'
                f'<span class="pageNumber"></span> / '
                f'<span class="totalPages"></span></div>',
            }
        )
    page.pdf(**options)


def page_index(pdf_path: Path, items: list[tuple[str, str, str]]) -> dict[str, int]:
    from pypdf import PdfReader

    pages = [re.sub(r"\s+", "", p.extract_text() or "") for p in PdfReader(str(pdf_path)).pages]
    where, start = {}, 0
    for level, num, title in items:
        key = re.sub(r"\s+", "", f"{num}{title}" if level in ("l1", "l2") else f"{num}.")
        for i in range(start if level in ("l1", "l2") else 0, len(pages)):
            if key[:40] in pages[i]:
                where[f"{level}:{num}"] = i + 1
                if level in ("l1", "l2"):
                    start = i
                break
    return where


def toc_html(items, where) -> tuple[str, str, str]:
    def li(cls, label, page):
        return (
            f'<li class="{cls}"><span class="t">{label}</span><span class="dots"></span>'
            f'<span class="p">{page}</span></li>'
        )

    toc = [
        li(lv, f"{num}&nbsp;&nbsp;{esc(t)}", where.get(f"{lv}:{num}", ""))
        for lv, num, t in items
        if lv in ("l1", "l2")
    ]
    lof = [li("l2", f"{num}. {esc(t)}", where.get(f"fig:{num}", "")) for lv, num, t in items if lv == "fig"]
    lot = [li("l2", f"{num}. {esc(t)}", where.get(f"tab:{num}", "")) for lv, num, t in items if lv == "tab"]
    wrap = lambda xs: "<ol>" + "".join(xs) + "</ol>"  # noqa: E731
    return wrap(toc), wrap(lof), wrap(lot)


def main() -> None:
    from playwright.sync_api import sync_playwright
    from pypdf import PdfReader, PdfWriter

    v = values()
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / "report.css").write_text((SRC / "report.css").read_text(encoding="utf-8"), encoding="utf-8")
    body = fill((SRC / "body.html").read_text(encoding="utf-8"), v)
    (BUILD / "body.html").write_text(body, encoding="utf-8")
    items = entries(body)
    title = html.unescape(v["document"])

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        render(page, BUILD / "body.html", BUILD / "body.pdf", numbered=True, title=title)
        where = page_index(BUILD / "body.pdf", items)
        missing = [f"{lv} {num}" for lv, num, _ in items if f"{lv}:{num}" not in where]
        if missing:
            print("warning: page not found for", missing)
        v["toc"], v["lof"], v["lot"] = toc_html(items, where)
        (BUILD / "front.html").write_text(
            fill((SRC / "front.html").read_text(encoding="utf-8"), v), encoding="utf-8"
        )
        render(page, BUILD / "front.html", BUILD / "front.pdf", numbered=False, title=title)
        browser.close()

    writer = PdfWriter()
    for part in ("front.pdf", "body.pdf"):
        for pg in PdfReader(str(BUILD / part)).pages:
            writer.add_page(pg)
    writer.add_metadata(
        {
            "/Title": html.unescape(v["title"]),
            "/Subject": title,
            "/Author": html.unescape(v["author"]),
            "/Keywords": "AIOps, LLM agents, verification",
        }
    )
    with OUT.open("wb") as f:
        writer.write(f)
    n_front, n_body = len(PdfReader(str(BUILD / "front.pdf")).pages), len(
        PdfReader(str(BUILD / "body.pdf")).pages
    )
    print(
        f"wrote {OUT.relative_to(REPO)}: {n_front} front + {n_body} body pages, "
        f"{len(where)}/{len(items)} contents entries located"
    )


if __name__ == "__main__":
    main()
