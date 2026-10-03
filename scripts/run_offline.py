#!/usr/bin/env python
"""`make run` -- Phase P2 acceptance (ARCHITECTURE_BLUEPRINT.md §8): an end-to-end run on the offline
fixtures produces RunRecords in DuckDB; destructive actions are blocked; correct ones are allowed.

    python scripts/run_offline.py --variant envelope --tau 0.5
    python scripts/run_offline.py --variant llm_judge          # needs Anthropic credentials

Uses config/offline_eval.yaml (the explicit auto_execute opt-in for the simulated env).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sentinel.config import REPO_ROOT, load_config, resolve_path  # noqa: E402
from sentinel.env.offline_adapter import OfflineEnvAdapter  # noqa: E402
from sentinel.orchestrator.factory import build_orchestrator  # noqa: E402
from sentinel.store.duckdb_store import DuckDBStore  # noqa: E402
from sentinel.verifier.policy import VARIANTS  # noqa: E402


def _outcome(run) -> str:
    if run.final_resolved:
        return "resolved"
    last = run.steps[-1].verdict.decision if run.steps else "-"
    return {"block": "escalated (blocked)", "revise": "gave up after revise"}.get(last, "unresolved")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--variant", choices=VARIANTS, default="envelope")
    parser.add_argument("--tau", type=float, default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--incident", action="append")
    parser.add_argument("--experiment", default="adhoc")
    args = parser.parse_args()

    config = load_config(REPO_ROOT / "config" / "offline_eval.yaml")
    env = OfflineEnvAdapter()
    store = DuckDBStore(resolve_path(config["store"]["path"]))
    orchestrator = build_orchestrator(config, env, variant=args.variant, tau=args.tau, seed=args.seed)
    tau = config["verifier"]["threshold"] if args.tau is None else args.tau
    print(f"variant={args.variant} tau={tau} agent={config['agent']['kind']} seed={args.seed}\n")

    for incident_id in args.incident or env.list_incidents():
        run = orchestrator.run(incident_id, seed=args.seed, dry_run=False)
        store.write_run(
            run,
            run_id=f"{args.experiment}:{args.variant}:{tau}:{args.seed}:{incident_id}",
            meta={
                "experiment": args.experiment,
                "variant": args.variant,
                "tau": tau,
                "agent_kind": config["agent"]["kind"],
            },
        )
        trail = "  ".join(
            f"{s.proposed.action_type}[{s.ground_truth_label or '?'}]->{s.verdict.decision}"
            for s in run.steps
        )
        flag = "  !! UNSAFE ACTION EXECUTED" if run.unsafe_action_reached_exec else ""
        print(f"{incident_id:28} {_outcome(run):22} {trail}{flag}")

    summary = store.query(
        "SELECT ground_truth_label AS label, decision, count(*) AS n FROM steps "
        "WHERE run_id LIKE ? GROUP BY ALL ORDER BY label, decision",
        [f"{args.experiment}:{args.variant}:{tau}:{args.seed}:%"],
    )
    print(f"\nfrom DuckDB ({store.path.relative_to(REPO_ROOT)}): label x decision")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
