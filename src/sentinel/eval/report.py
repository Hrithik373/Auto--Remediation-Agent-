# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Rebuilds every reported table (baselines, partition, Pareto, ablations) from DuckDB.
# Shared by scripts/run_eval.py and the /api/experiments endpoints, so both always agree.
"""Rebuilds every reported number from the DuckDB store (blueprint §7, CLAUDE.md "make eval must
regenerate every figure from scratch"). Used by scripts/run_eval.py and by the console API (P5d), so
the report and the Results screen can never disagree.

Uncertainty: 95% bootstrap CIs resample INCIDENTS (all seeds of an incident together), because seeds of
one incident are not independent evidence. Seeded, so CIs are reproducible too.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from sentinel.eval import metrics as M
from sentinel.eval.pareto import pareto_front, sweep_threshold
from sentinel.schemas.run import RunRecord
from sentinel.store.duckdb_store import DuckDBStore

CI_METRICS = {
    "resolution": M.resolution_rate,
    "bad_action_prevented": M.bad_action_prevented_rate,
    "false_block": M.false_block_rate,
    "unsafe_execution": M.unsafe_execution_rate,
    "net_safe_resolutions": M.net_safe_resolutions,
}
BASELINE_ORDER = ["none", "react_ungated", "envelope", "llm_judge", "learned", "combined"]
DISPLAY = {
    "none": "Ungated agent",
    "react_ungated": "ReAct (ungated)",
    "envelope": "Envelope only",
    "llm_judge": "Envelope + LLM judge",
    "learned": "Envelope + learned",
    "combined": "Envelope + judge + learned",
}


def bootstrap_ci(runs: list[RunRecord], metric, *, resamples: int, seed: int) -> tuple[float, float] | None:
    by_incident: dict[str, list[RunRecord]] = defaultdict(list)
    for run in runs:
        by_incident[run.incident_id].append(run)
    keys = sorted(by_incident)
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(resamples):
        sample = [r for k in rng.choice(keys, size=len(keys), replace=True) for r in by_incident[k]]
        value = metric(sample)
        if value is not None:
            values.append(value)
    if not values:
        return None
    lo, hi = np.percentile(values, [2.5, 97.5])
    return round(float(lo), 4), round(float(hi), 4)


def _round(d: dict) -> dict:
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}


def _group(rows: list[tuple[dict, RunRecord]], cell: str, key) -> dict:
    groups: dict = defaultdict(list)
    for meta, run in rows:
        if meta.get("cell") == cell:
            groups[key(meta)].append(run)
    return groups


def baselines_table(rows, *, resamples: int, seed: int) -> list[dict]:
    groups = _group(rows, "baselines", lambda m: m["label"])
    table = []
    for label in sorted(groups, key=lambda x: BASELINE_ORDER.index(x) if x in BASELINE_ORDER else 99):
        runs = groups[label]
        entry = {"baseline": DISPLAY.get(label, label), "variant": label, **_round(M.summarize(runs))}
        for name, fn in CI_METRICS.items():
            entry[f"{name}_ci95"] = bootstrap_ci(runs, fn, resamples=resamples, seed=seed)
        table.append(entry)
    return table


def partition_table(rows) -> list[dict]:
    groups = _group(rows, "baselines", lambda m: m["label"])
    out = []
    for label in sorted(groups, key=lambda x: BASELINE_ORDER.index(x) if x in BASELINE_ORDER else 99):
        part = M.prevention_partition(groups[label])
        if part is not None:
            out.append({"baseline": DISPLAY.get(label, label), "variant": label, **_round(part)})
    return out


def pareto_series(rows) -> dict[str, list[dict]]:
    groups = _group(rows, "pareto", lambda m: (m["label"], m["tau"]))
    series: dict[str, dict[float, list[RunRecord]]] = defaultdict(dict)
    for (label, tau), runs in groups.items():
        series[label][tau] = runs
    return {label: [_round(p) for p in sweep_threshold(by_tau)] for label, by_tau in sorted(series.items())}


def ablation_rows(rows) -> list[dict]:
    out = []

    def add(name, label, runs, metric_names):
        summary = M.summarize(runs)
        out.extend(
            {"name": name, "variant": label, "metric": m, "value": _round(summary)[m]} for m in metric_names
        )

    base = _group(rows, "baselines", lambda m: m["label"])
    for label in ("none", "learned"):
        if label in base:
            add(
                "Verifier on/off",
                "off (ungated)" if label == "none" else "on (envelope + learned)",
                base[label],
                ["unsafe_execution", "resolution", "net_safe_resolutions"],
            )
    for label in ("envelope", "llm_judge", "learned", "combined"):
        if label in base:
            add("Verification layers", DISPLAY[label], base[label], ["bad_action_prevented", "false_block"])
    topo = _group(rows, "topology_features", lambda m: m["label"])
    if "learned" in base and "learned_no_topology" in topo:
        add(
            "Topology features (learned)",
            "with topology",
            base["learned"],
            ["bad_action_prevented", "false_block"],
        )
        add(
            "Topology features (learned)",
            "without topology",
            topo["learned_no_topology"],
            ["bad_action_prevented", "false_block"],
        )
    retry = _group(rows, "block_policy", lambda m: m["label"])
    for variant in ("envelope", "learned"):
        if variant in base and f"{variant}+retry" in retry:
            metric_names = ["resolution", "unsafe_execution", "net_safe_resolutions", "steps_to_mitigation"]
            add("Block handling", f"{DISPLAY[variant]}: escalate", base[variant], metric_names)
            add("Block handling", f"{DISPLAY[variant]}: retry", retry[f"{variant}+retry"], metric_names)
    for label, runs in sorted(_group(rows, "agent_quality", lambda m: m["label"]).items()):
        add("Agent quality", label, runs, ["unsafe_execution", "resolution", "net_safe_resolutions"])
    return out


def build_results(
    store: DuckDBStore,
    experiment: str,
    *,
    resamples: int = 1000,
    seed: int = 0,
    models_dir: Path | None = None,
    skipped: list[dict] | None = None,
) -> dict:
    rows = store.read_runs_with_meta(experiment)
    results = {
        "experiment": experiment,
        "n_runs": len(rows),
        "config_hashes": sorted({run.config_hash for _, run in rows}),
        "baselines": baselines_table(rows, resamples=resamples, seed=seed),
        "prevention_partition": partition_table(rows),
        "pareto": pareto_series(rows),
        "ablations": ablation_rows(rows),
        "skipped": skipped or [],
    }
    results["pareto_front"] = {k: pareto_front(v) for k, v in results["pareto"].items()}
    metrics_path = (models_dir / "learned_verifier_metrics.json") if models_dir else None
    if metrics_path and metrics_path.exists():
        results["learned_verifier_training"] = json.loads(metrics_path.read_text(encoding="utf-8"))
    return results


def _fmt(value, ci=None) -> str:
    if value is None:
        return "n/a"
    text = f"{value:.3f}" if isinstance(value, float) else str(value)
    return f"{text} [{ci[0]:.3f}, {ci[1]:.3f}]" if ci else text


def to_markdown(results: dict) -> str:
    lines = [
        f"# Evaluation results -- experiment `{results['experiment']}`",
        "",
        f"{results['n_runs']} runs across {len(results['config_hashes'])} distinct resolved configs "
        "(one per cell x seed; each run's config_hash is in DuckDB).",
        "",
        "## Baselines (95% bootstrap CI over incidents)",
        "",
        "| Baseline | Resolution | Bad-action prevented | False block | Unsafe exec | Net safe | Steps |",
        "|---|---|---|---|---|---|---|",
    ]
    for b in results["baselines"]:
        lines.append(
            f"| {b['baseline']} | {_fmt(b['resolution'], b['resolution_ci95'])} | "
            f"{_fmt(b['bad_action_prevented'], b['bad_action_prevented_ci95'])} | "
            f"{_fmt(b['false_block'], b['false_block_ci95'])} | "
            f"{_fmt(b['unsafe_execution'], b['unsafe_execution_ci95'])} | "
            f"{_fmt(b['net_safe_resolutions'], b['net_safe_resolutions_ci95'])} | "
            f"{_fmt(b['steps_to_mitigation'])} |"
        )
    lines += [
        "",
        "## Prevention partition (destructive proposals)",
        "",
        "| Baseline | Caught by envelope | Caught by secondary only | Missed |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {p['baseline']} | {p['caught_by_envelope']:.3f} | {p['caught_by_secondary_only']:.3f} | "
        f"{p['missed']:.3f} |"
        for p in results["prevention_partition"]
    ]
    lines += ["", "## Ablations", "", "| Ablation | Variant | Metric | Value |", "|---|---|---|---|"]
    lines += [
        f"| {a['name']} | {a['variant']} | {a['metric']} | {_fmt(a['value'])} |" for a in results["ablations"]
    ]
    if results["skipped"]:
        lines += ["", "## Not run (stated, not omitted)", ""]
        lines += [f"- **{s['cell']} / {s['name']}** -- {s['reason']}" for s in results["skipped"]]
    return "\n".join(lines) + "\n"
