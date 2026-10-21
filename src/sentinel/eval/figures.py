# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Draws the report figures (Pareto, prevention partition, reliability, agent quality).
# Reads only report.py's results dict, never in-memory runs.
"""Report figures, rendered from eval/report.py's results dict (never from in-memory runs), so
`make eval` regenerates every figure from DuckDB (CLAUDE.md).

Colors follow the dataviz skill and were run through its validate_palette.js against the light print
surface #fcfcfb -- do not change a hex without re-running it:
  * series identity is fixed per ENTITY across every figure (envelope=blue, learned=orange,
    llm_judge=aqua, ungated=magenta), never by rank;
  * Pareto lines (blue/orange/aqua): all-pairs PASS; aqua < 3:1 contrast -> direct end labels;
  * partition stack (blue/violet/critical red): adjacent PASS at full contrast; orange next to red
    FAILED the normal-vision floor, so the "secondary layer" segment is violet, not orange;
  * agent-quality bars (magenta/blue/orange, in that order): adjacent PASS; magenta < 3:1 ->
    value labels on every bar. (Gray for "ungated" failed the chroma floor.)
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: figures are files, never windows
import joblib  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

SURFACE, INK, INK_2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
SERIES = {
    "envelope": "#2a78d6",
    "learned": "#eb6834",
    "llm_judge": "#1baf7a",
    "none": "#e87ba4",
    "combined": "#4a3aa7",
}
NAMES = {
    "envelope": "Envelope only",
    "learned": "Envelope + learned",
    "llm_judge": "Envelope + LLM judge",
    "none": "Ungated agent",
    "combined": "Envelope + judge + learned",
}
PARTITION = [
    ("caught_by_envelope", "Caught by envelope", "#2a78d6"),
    ("caught_by_secondary_only", "Caught by secondary layer only", "#4a3aa7"),
    ("missed", "Missed (reached the executor)", "#d03b3b"),
]


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "font.family": "sans-serif",
            "font.sans-serif": ["Segoe UI", "Helvetica", "Arial", "DejaVu Sans"],
            "font.size": 9,
            "axes.edgecolor": AXIS,
            "axes.labelcolor": INK_2,
            "axes.titlecolor": INK,
            "axes.titlesize": 10,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "axes.axisbelow": True,  # grid recedes behind data
            "axes.spines.top": False,
            "axes.spines.right": False,
            "legend.frameon": False,
            "legend.labelcolor": INK_2,
        }
    )


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def _percent_axis(ax, axis: str = "both") -> None:
    fmt = matplotlib.ticker.PercentFormatter(1.0, decimals=0)
    if axis in ("x", "both"):
        ax.xaxis.set_major_formatter(fmt)
    if axis in ("y", "both"):
        ax.yaxis.set_major_formatter(fmt)


def pareto_figure(results: dict, path: Path, default_tau: float = 0.5) -> Path:
    """(a) bad-action-prevented vs false-block across tau; (b) resolution vs tau. One axis per panel."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.6), gridspec_kw={"wspace": 0.28})
    for variant, points in results["pareto"].items():
        pts = [p for p in points if p["false_block"] is not None and p["bad_action_prevented"] is not None]
        color, name = SERIES.get(variant, INK_2), NAMES.get(variant, variant)
        xs, ys = [p["false_block"] for p in pts], [p["bad_action_prevented"] for p in pts]
        ax1.plot(xs, ys, color=color, lw=1.6, marker="o", ms=4.5, mec=SURFACE, mew=1.2, label=name, zorder=3)
        here = next((p for p in pts if abs(p["tau"] - default_tau) < 1e-9), None)
        if here:  # leader line keeps the label off clustered markers
            ax1.annotate(
                f"τ={default_tau:g}",
                (here["false_block"], here["bad_action_prevented"]),
                xytext=(28, -22),
                textcoords="offset points",
                color=INK_2,
                fontsize=8,
                arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 0.7},
            )
        ax2.plot(
            [p["tau"] for p in points],
            [p["resolution"] for p in points],
            color=color,
            lw=1.6,
            marker="o",
            ms=4.5,
            mec=SURFACE,
            mew=1.2,
            label=name,
            zorder=3,
        )
        ax2.annotate(
            name,
            (points[-1]["tau"], points[-1]["resolution"]),
            xytext=(5, 0),
            textcoords="offset points",
            va="center",
            color=INK_2,
            fontsize=8,
        )
    ax1.set(
        xlabel="False-block rate (correct actions stopped)",
        ylabel="Bad actions prevented",
        title="Risk–autonomy trade-off across τ",
        xlim=(-0.03, 1.03),
        ylim=(-0.03, 1.05),
    )
    ax2.set(xlabel="Threshold τ", ylabel="Incidents resolved", title="Resolution vs τ", ylim=(-0.03, 1.05))
    _percent_axis(ax1)
    _percent_axis(ax2, "y")
    ax1.legend(loc="lower right")
    return _save(fig, path)


def partition_figure(results: dict, path: Path) -> Path:
    """★ The thesis figure: where each destructive proposal was stopped, per baseline."""
    rows = results["prevention_partition"]
    fig, ax = plt.subplots(figsize=(8.0, 0.55 * len(rows) + 1.3))
    y = np.arange(len(rows))[::-1]
    left = np.zeros(len(rows))
    for key, label, color in PARTITION:
        widths = np.array([r[key] for r in rows])
        ax.barh(y, widths, left=left, color=color, height=0.56, edgecolor=SURFACE, linewidth=1.5, label=label)
        for yi, start, w in zip(y, left, widths):
            if w >= 0.08:  # label inside only when the text fits
                ax.text(start + w / 2, yi, f"{w:.0%}", ha="center", va="center", color="#ffffff", fontsize=8)
        left += widths
    ax.set_yticks(y, [r["baseline"] for r in rows], color=INK_2)
    ax.set(
        xlim=(0, 1), xlabel="Share of destructive proposals", title="Where destructive actions were stopped"
    )
    ax.grid(axis="y", visible=False)
    _percent_axis(ax, "x")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=3)
    return _save(fig, path)


def reliability_figure(models_dir: Path, path: Path, bins: int = 10) -> Path | None:
    """Calibration of the learned verifier's out-of-fold P(destructive)."""
    bundle_path = models_dir / "learned_verifier.joblib"
    if not bundle_path.exists():
        return None
    oof = joblib.load(bundle_path)["oof"]
    y, p = np.array(oof["y"]), np.array(oof["p"])
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    used = [b for b in range(bins) if (idx == b).any()]
    counts = np.array([(idx == b).sum() for b in used])
    fig, (ax, axh) = plt.subplots(
        2, 1, figsize=(4.6, 4.8), sharex=True, gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08}
    )
    ax.plot([0, 1], [0, 1], color=AXIS, lw=1, ls="--", label="Perfect calibration")
    # Unconnected dots sized by bin count: most predictions sit near 0 or 1, and joining sparse middle
    # bins (n of 1-7) with a line would draw noise as if it were systematic miscalibration.
    px, py = [p[idx == b].mean() for b in used], [y[idx == b].mean() for b in used]
    ax.scatter(
        px,
        py,
        s=18 + 160 * counts / counts.max(),
        color=SERIES["learned"],
        edgecolors=SURFACE,
        linewidths=1.2,
        zorder=3,
        label="Learned verifier (out-of-fold)",
    )
    for x_, y_, n in zip(px, py, counts):
        ax.annotate(f"n={n}", (x_, y_), xytext=(7, 4), textcoords="offset points", fontsize=7, color=INK_2)
    ax.set(ylabel="Observed destructive rate", title="Calibration of P(destructive)", ylim=(-0.06, 1.08))
    ax.legend(loc="upper left")
    axh.bar(
        [(edges[b] + edges[b + 1]) / 2 for b in used],
        [(idx == b).sum() for b in used],
        width=0.09,
        color=SERIES["learned"],
        edgecolor=SURFACE,
        linewidth=1.5,
    )
    axh.set(xlabel="Predicted P(destructive)", ylabel="Proposals", xlim=(-0.02, 1.02))
    axh.grid(axis="x", visible=False)
    return _save(fig, path)


def agent_quality_figure(results: dict, path: Path) -> Path | None:
    """Unsafe-execution and net-safe-resolution rates as the planner gets worse."""
    rows = [a for a in results["ablations"] if a["name"] == "Agent quality"]
    if not rows:
        return None
    mixes = [m for m in ("strong", "default", "weak") if any(r["variant"].endswith("@" + m) for r in rows)]
    variants = ["none", "envelope", "learned"]
    value = {(r["variant"], r["metric"]): r["value"] for r in rows}
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.4), gridspec_kw={"wspace": 0.25})
    width, x = 0.26, np.arange(len(mixes))
    for ax, metric, title in zip(
        axes,
        ("unsafe_execution", "net_safe_resolutions"),
        ("Runs where a destructive action executed", "Resolved with no destructive action"),
    ):
        for i, variant in enumerate(variants):
            heights = [value.get((f"{variant}@{m}", metric)) or 0.0 for m in mixes]
            bars = ax.bar(
                x + (i - 1) * width,
                heights,
                width=width,
                color=SERIES[variant],
                edgecolor=SURFACE,
                linewidth=1.5,
                label=NAMES[variant],
            )
            ax.bar_label(bars, labels=[f"{h:.0%}" for h in heights], padding=2, fontsize=7, color=INK_2)
        ax.set_xticks(x, [f"{m} planner" for m in mixes], color=INK_2)
        ax.set(title=title, ylim=(0, 1.08))
        ax.grid(axis="x", visible=False)
        _percent_axis(ax, "y")
    axes[0].legend(loc="upper left")
    return _save(fig, path)


def render_all(results: dict, out_dir: Path, *, models_dir: Path) -> list[Path]:
    _style()
    made = [
        pareto_figure(results, out_dir / "pareto.png"),
        partition_figure(results, out_dir / "prevention_partition.png"),
        reliability_figure(models_dir, out_dir / "reliability.png"),
        agent_quality_figure(results, out_dir / "agent_quality.png"),
    ]
    return [p for p in made if p is not None]
