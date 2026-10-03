#!/usr/bin/env python
"""`make eval` -- Phase P4 acceptance (ARCHITECTURE_BLUEPRINT.md §8): one command reproduces the
Pareto figure and ablation tables FROM SCRATCH with a fixed seed set.

  1. retrain the learned verifier (seeded)            -> runs/models/
  2. wipe this experiment's rows, run every cell       -> RunRecords in runs/sentinel.duckdb
  3. rebuild all tables + figures from DuckDB          -> runs/eval/{results.json, results.md, figures/}

LLM-backed baselines (judge, ReAct agent) run only with --with-llm, because they spend money; without
it they are listed under "Not run" in the report rather than silently omitted.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sentinel.config import REPO_ROOT, load_config, resolve_path  # noqa: E402
from sentinel.env.offline_adapter import OfflineEnvAdapter  # noqa: E402
from sentinel.eval.ablations import plan  # noqa: E402
from sentinel.eval.report import build_results, to_markdown  # noqa: E402
from sentinel.eval.runner import run_grid  # noqa: E402
from sentinel.store.duckdb_store import DuckDBStore  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--with-llm", action="store_true", help="also run LLM-backed baselines (costs money)")
    parser.add_argument("--skip-train", action="store_true", help="reuse runs/models (default: retrain)")
    parser.add_argument("--report-only", action="store_true", help="rebuild tables/figures from DuckDB only")
    args = parser.parse_args()

    config = load_config(REPO_ROOT / "config" / "offline_eval.yaml")
    ev = config["eval"]
    models_dir = resolve_path(config["verifier"]["learned_model_path"]).parent
    out_dir = resolve_path(ev["output_dir"])
    store = DuckDBStore(resolve_path(config["store"]["path"]))
    env = OfflineEnvAdapter()

    if not (args.skip_train or args.report_only):
        subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "train_learned.py")], check=True)
    cells, skipped = plan(config, models_dir=models_dir, with_llm=args.with_llm)

    if not args.report_only:
        removed = store.delete_experiment(ev["experiment"])
        incidents, seeds = env.list_incidents(), ev["seeds"]
        print(
            f"eval: {len(cells)} cells x {len(incidents)} incidents x {len(seeds)} seeds "
            f"(cleared {removed} old runs)"
        )
        start = time.perf_counter()
        run_grid(
            env,
            incidents,
            seeds,
            config,
            cells=cells,
            experiment=ev["experiment"],
            store=store,
            progress=lambda i, n, c: (
                print(f"  [{i:>3}/{n}] {c.cell:18} {c.name:24} tau={c.tau:.2f}", flush=True)
                if i % 10 == 0 or i == n
                else None
            ),
        )
        print(f"grid done in {time.perf_counter() - start:.0f}s")

    results = build_results(
        store,
        ev["experiment"],
        resamples=ev["bootstrap_resamples"],
        seed=config["orchestrator"]["seed"],
        models_dir=models_dir,
        skipped=skipped,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (out_dir / "results.md").write_text(to_markdown(results), encoding="utf-8")
    from sentinel.eval.figures import render_all  # lazy: matplotlib only needed here

    figures = render_all(results, out_dir / "figures", models_dir=models_dir)
    print(to_markdown(results))
    print("figures:", ", ".join(p.name for p in figures))


if __name__ == "__main__":
    main()
