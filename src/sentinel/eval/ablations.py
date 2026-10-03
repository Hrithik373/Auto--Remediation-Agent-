"""The experiment plan (blueprint §7): five baselines, the tau sweep, and the ablations -- as Cells for
eval/runner.py. What runs offline vs. what needs the LLM is decided HERE, and the skipped entries are
returned too, so the report states them instead of silently omitting them.

Baselines (blueprint §7):
  1. ungated agent           -> variant "none"
  2. ReAct baseline          -> needs the LLM agent (agent.kind=react)            [--with-llm]
  3. envelope-only           -> variant "envelope"
  4. LLM-judge verifier (v1) -> variant "llm_judge"                               [--with-llm]
  5. learned verifier (v2)   -> variant "learned"  (+ "combined" = both, with --with-llm)

Ablations:
  * verifier on/off and layer composition -- read off the baselines (no extra runs)
  * tau sweep -- the Pareto cells
  * topology features -- learned vs learned retrained without topology features (ITBench topology is
    curated around the fault, so this is the threat-to-validity check)
  * block handling -- escalate on block (blueprint default) vs retry with the block reasons as feedback
  * agent quality -- strong / default / weak simulated planner x {none, envelope, learned}
  * telemetry-signal and model-size sweeps -- need the LLM agent / judge          [--with-llm]
"""

from __future__ import annotations

from pathlib import Path

from sentinel.eval.runner import Cell
from sentinel.verifier.learned import LearnedVerifier

LLM_VARIANTS = ("llm_judge", "combined")


def plan(config: dict, *, models_dir: Path, with_llm: bool) -> tuple[list[Cell], list[dict]]:
    ev = config["eval"]
    tau = ev["default_tau"]
    learned = LearnedVerifier(model_path=models_dir / "learned_verifier.joblib")
    no_topo = LearnedVerifier(model_path=models_dir / "learned_verifier_no_topology.joblib")
    cells: list[Cell] = []
    skipped: list[dict] = []

    for variant in ("none", "envelope", "learned", *LLM_VARIANTS):
        if variant in LLM_VARIANTS and not with_llm:
            skipped.append(
                {"cell": "baselines", "name": variant, "reason": "needs the LLM judge (--with-llm)"}
            )
            continue
        cells.append(
            Cell("baselines", variant, tau, learned=learned if variant in ("learned", "combined") else None)
        )
    if with_llm:
        cells.append(
            Cell(
                "baselines", "none", tau, label="react_ungated", config_overrides={"agent": {"kind": "react"}}
            )
        )
    else:
        skipped.append(
            {"cell": "baselines", "name": "react_ungated", "reason": "needs the LLM ReAct agent (--with-llm)"}
        )

    for variant in ev["pareto_variants"] + (["llm_judge"] if with_llm else []):
        for t in ev["tau_grid"]:
            cells.append(Cell("pareto", variant, t, learned=learned if variant == "learned" else None))

    cells.append(Cell("topology_features", "learned", tau, label="learned_no_topology", learned=no_topo))

    # Block handling: the blueprint escalates on every block; "retry" feeds the block reasons back to
    # the agent instead. Separates "the verifier blocks fixes" from "the loop gives up after a block".
    for variant in ("envelope", "learned"):
        cells.append(
            Cell(
                "block_policy",
                variant,
                tau,
                label=f"{variant}+retry",
                learned=learned if variant == "learned" else None,
                config_overrides={"orchestrator": {"on_block": "retry"}},
            )
        )

    for mix_name, mix in ev["agent_mixes"].items():
        for variant in ("none", "envelope", "learned"):
            cells.append(
                Cell(
                    "agent_quality",
                    variant,
                    tau,
                    label=f"{variant}@{mix_name}",
                    learned=learned if variant == "learned" else None,
                    config_overrides={"agent": {"simulated": {"label_mix": mix}}},
                )
            )

    if not with_llm:
        skipped += [
            {
                "cell": "telemetry_signal",
                "name": "logs-only vs all signals",
                "reason": "the simulated agent ignores telemetry; needs the LLM ReAct agent (--with-llm)",
            },
            {
                "cell": "model_size",
                "name": "agent/judge model sweep",
                "reason": "needs LLM calls (--with-llm)",
            },
        ]
    return cells, skipped
