"""Phase P4: grid runner -> DuckDB -> report rebuild, on a small grid (2 incidents, 1 seed)."""

from __future__ import annotations

import pytest

from sentinel.config import REPO_ROOT, load_config
from sentinel.env.offline_adapter import OfflineEnvAdapter
from sentinel.eval.pareto import pareto_front
from sentinel.eval.report import build_results, to_markdown
from sentinel.eval.runner import Cell, run_grid
from sentinel.labeling.dataset import build_dataset
from sentinel.store.duckdb_store import DuckDBStore
from sentinel.verifier.learned import LearnedVerifier, train_bundle

INCIDENTS = ["bad-rollout-latency", "itbench-sre-scenario-12"]


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    env = OfflineEnvAdapter()
    config = load_config(REPO_ROOT / "config" / "offline_eval.yaml")
    rows = build_dataset(env)
    learned = LearnedVerifier(
        bundle=train_bundle(rows, {i: env.get_incident(i) for i in env.list_incidents()}, n_folds=3)
    )
    cells = [
        Cell("baselines", "none", 0.5),
        Cell("baselines", "envelope", 0.5),
        Cell("baselines", "learned", 0.5, learned=learned),
        *[Cell("pareto", "envelope", t) for t in (0.2, 0.5)],
        Cell(
            "block_policy",
            "learned",
            0.5,
            label="learned+retry",
            learned=learned,
            config_overrides={"orchestrator": {"on_block": "retry"}},
        ),
    ]
    store = DuckDBStore(tmp_path_factory.mktemp("eval") / "runs.duckdb")
    run_grid(env, INCIDENTS, [0], config, cells=cells, experiment="t", store=store)
    run_grid(env, INCIDENTS, [0], config, cells=cells, experiment="t", store=store)  # idempotent rerun
    return build_results(
        store,
        "t",
        resamples=50,
        seed=0,
        skipped=[{"cell": "baselines", "name": "llm_judge", "reason": "no LLM"}],
    )


def test_every_run_is_persisted_once(results):
    assert results["n_runs"] == 6 * len(INCIDENTS)  # the rerun replaced rows instead of duplicating them


def test_report_tables_cover_baselines_partition_pareto_ablations(results):
    assert [b["variant"] for b in results["baselines"]] == ["none", "envelope", "learned"]
    assert all(b["resolution_ci95"] is not None for b in results["baselines"])
    assert set(results["pareto"]) == {"envelope"} and [p["tau"] for p in results["pareto"]["envelope"]] == [
        0.2,
        0.5,
    ]
    for row in results["prevention_partition"]:
        parts = row["caught_by_envelope"] + row["caught_by_secondary_only"] + row["missed"]
        assert parts == pytest.approx(1.0, abs=1e-3)
    assert {a["name"] for a in results["ablations"]} >= {"Verifier on/off", "Block handling"}


def test_skipped_cells_are_stated_in_the_report(results):
    assert "Not run (stated, not omitted)" in to_markdown(results)
    assert "llm_judge" in to_markdown(results)


def test_pareto_front_drops_dominated_points():
    points = [
        {"false_block": 0.0, "bad_action_prevented": 0.4},
        {"false_block": 0.1, "bad_action_prevented": 0.9},
        {"false_block": 0.2, "bad_action_prevented": 0.8},
    ]
    assert pareto_front(points) == points[:2]
