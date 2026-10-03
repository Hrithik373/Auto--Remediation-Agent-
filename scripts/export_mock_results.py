#!/usr/bin/env python
"""`make mock-results` -- snapshots runs/eval/results.json (from `make eval`) into the console's mock
layer (frontend/src/mock/experiments.json), so mock mode shows MEASURED numbers instead of
illustrative ones. The shapes are exactly what gateway/api.py's /api/experiments/* return; the file
records which experiment and config hashes it came from. Re-run after every `make eval`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sentinel.config import REPO_ROOT, load_config, resolve_path  # noqa: E402

OUT = REPO_ROOT / "frontend" / "src" / "mock" / "experiments.json"


def main() -> None:
    config = load_config()
    results_path = resolve_path(config["eval"]["output_dir"]) / "results.json"
    if not results_path.exists():
        sys.exit(f"{results_path} not found -- run `make eval` first")
    r = json.loads(results_path.read_text(encoding="utf-8"))
    snapshot = {
        "source": f"snapshot of `make eval` experiment '{r['experiment']}' ({r['n_runs']} runs)",
        "pareto": r["pareto"],
        "metrics": [
            {
                "baseline": b["baseline"],
                "variant": b["variant"],
                "resolution": b["resolution"],
                "bad_prevented": b["bad_action_prevented"],
                "false_block": b["false_block"],
                "unsafe_execution": b["unsafe_execution"],
                "mttm_ms": b["mttm_ms"],
                "cost_usd": b["cost_usd"],
            }
            for b in r["baselines"]
        ],
        "prevention_partition": r["prevention_partition"],
        "ablations": r["ablations"],
    }
    OUT.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO_ROOT)} ({snapshot['source']})")


if __name__ == "__main__":
    main()
