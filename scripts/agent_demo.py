#!/usr/bin/env python
"""`make agent` -- the Phase P1 acceptance check (ARCHITECTURE_BLUEPRINT.md §8):

    "agent produces a structured action for every fixture; executor logs a dry-run ExecutionResult;
     no action can reach 'apply' yet."

Uses config `agent.kind` (default: simulated, offline). `--agent react` uses the LLM ReAct agent and
needs Anthropic credentials; its calls go through the disk cache in runs/llm_cache.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sentinel.agent.base import AgentExhausted  # noqa: E402
from sentinel.agent.factory import build_agent  # noqa: E402
from sentinel.config import load_config  # noqa: E402
from sentinel.env.offline_adapter import OfflineEnvAdapter  # noqa: E402
from sentinel.executor.executor import ExecutionRefused, Executor  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--agent", choices=["simulated", "react"], help="override config agent.kind")
    parser.add_argument("--incident", action="append", help="limit to these incident ids")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    config = load_config(overrides={"agent": {"kind": args.agent}} if args.agent else None)
    env = OfflineEnvAdapter()
    agent = build_agent(config, env, seed=args.seed)
    executor = Executor(env)  # auto_execute defaults to False
    incidents = args.incident or env.list_incidents()
    print(
        f"agent={config['agent']['kind']}  incidents={len(incidents)}  auto_execute={executor.auto_execute}\n"
    )

    ok = 0
    for incident_id in incidents:
        incident = env.get_incident(incident_id)
        try:
            action = agent.propose(incident)
        except AgentExhausted as exc:
            print(f"{incident_id:32} NO PROPOSAL: {exc}")
            continue
        result = executor.run(action, dry_run=True)
        ok += 1
        print(
            f"{incident_id:32} {action.action_type:24} -> {action.target[:34]:34} "
            f"dry_run={result.dry_run} executed={result.executed}"
        )

    try:  # P1: prove the apply path is closed
        executor.run(action, dry_run=False)  # noqa: F821 -- last proposal
        print("\nERROR: a real apply went through")
        sys.exit(1)
    except ExecutionRefused as exc:
        print(f"\nreal apply refused as required: {exc}")
    print(
        f"structured proposals: {ok}/{len(incidents)}  tokens={agent.usage.total_tokens} "
        f"cost_usd={agent.usage.cost_usd:.4f}"
    )
    sys.exit(0 if ok == len(incidents) else 1)


if __name__ == "__main__":
    main()
