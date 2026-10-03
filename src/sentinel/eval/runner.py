"""Runs the grid: incidents x seeds x (variant, tau, agent config) -> RunRecords in DuckDB (blueprint §7).

Every run is written with metadata naming its experiment, cell, variant, tau, seed and agent, so the
report (eval/report.py) and the console API rebuild every number from the store -- nothing is
computed in memory and then lost (CLAUDE.md: no result exists unless it is a RunRecord row).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sentinel.config import config_hash, deep_merge
from sentinel.env.base import EnvAdapter
from sentinel.orchestrator.factory import build_orchestrator
from sentinel.schemas.run import RunRecord
from sentinel.store.duckdb_store import DuckDBStore
from sentinel.verifier.base import Verifier


@dataclass
class Cell:
    """One configuration to run over every incident x seed."""

    cell: str  # which experiment block: baselines | pareto | topology_features | agent_quality ...
    variant: str  # none | envelope | llm_judge | learned | combined
    tau: float
    label: str = ""  # display name; defaults to the variant
    learned: Verifier | None = None  # pre-loaded learned verifier (a bundle per ablation)
    config_overrides: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.label or self.variant


def run_id(experiment: str, cell: Cell, seed: int, incident_id: str) -> str:
    return f"{experiment}|{cell.cell}|{cell.name}|tau={cell.tau:.2f}|seed={seed}|{incident_id}"


def run_cell(
    env: EnvAdapter,
    config: dict,
    cell: Cell,
    *,
    experiment: str,
    seeds: list[int],
    incident_ids: list[str],
    store: DuckDBStore,
) -> list[RunRecord]:
    cfg = deep_merge(config, cell.config_overrides)
    runs, batch = [], []
    for seed in seeds:
        orchestrator = build_orchestrator(
            cfg, env, variant=cell.variant, tau=cell.tau, seed=seed, learned=cell.learned
        )
        for incident_id in incident_ids:
            run = orchestrator.run(incident_id, seed=seed, dry_run=not cfg["execution"]["auto_execute"])
            meta = {
                "experiment": experiment,
                "cell": cell.cell,
                "variant": cell.variant,
                "label": cell.name,
                "tau": cell.tau,
                "seed": seed,
                "agent_kind": cfg["agent"]["kind"],
                "cell_config_hash": config_hash(cfg),
            }
            batch.append((run_id(experiment, cell, seed, incident_id), run, meta))
            runs.append(run)
    store.write_runs(batch)
    return runs


def run_grid(
    env: EnvAdapter,
    incident_ids: list[str],
    seeds: list[int],
    config: dict,
    *,
    cells: list[Cell],
    experiment: str,
    store: DuckDBStore,
    progress=None,
) -> list[RunRecord]:
    runs: list[RunRecord] = []
    for i, cell in enumerate(cells, 1):
        runs.extend(
            run_cell(
                env, config, cell, experiment=experiment, seeds=seeds, incident_ids=incident_ids, store=store
            )
        )
        if progress:
            progress(i, len(cells), cell)
    return runs
