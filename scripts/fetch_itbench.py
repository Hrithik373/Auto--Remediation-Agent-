#!/usr/bin/env python
"""One-time, selective download of ibm-research/ITBench-Lite's SRE snapshots (Apache-2.0).

This is the separate fetch step docs/tasks/itbench_converter_spec.md §4 asks for -- convert_itbench.py
never downloads anything itself, so the mapping tables can be iterated on without re-fetching.

The full snapshots/sre tree is ~31 GB, ~18 GB of which is per-pod/per-service metrics the converter
mostly doesn't need. So this fetches in two passes:
  1. small files for every scenario (ground_truth.yaml, alerts, k8s events, status) -- ~0.5 GB;
  2. with --with-telemetry: otel logs + traces, and ONLY the service_<name>_raw.tsv metrics files
     for services that actually alerted in that scenario (resolved from pass 1's alert files).

Raw data lands under data/ (gitignored). Never commit it -- only fixtures/incidents/*.json is committed.
Re-running is safe: files already on disk are skipped. If the Xet transfer backend errors on large
files (seen on Windows as "File reconstruction error ... os error 483"), set HF_HUB_DISABLE_XET=1 to
fall back to plain HTTP downloads.

    python scripts/fetch_itbench.py                                  # pass 1, all scenarios
    python scripts/fetch_itbench.py --with-telemetry --scenario Scenario-1
    python scripts/fetch_itbench.py --with-telemetry                 # pass 2, all 35 (~12 GB)
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from itbench_common import alerted_services, load_ground_truth  # noqa: E402

REPO_ID = "ibm-research/ITBench-Lite"
SRE_PREFIX = "snapshots/sre"
SMALL_FILES = ("ground_truth.yaml", "status.json", "assertion.json", "k8s_events_raw.tsv")
TELEMETRY_FILES = ("otel_logs_raw.tsv", "otel_traces_raw.tsv")


def _list_sre_files() -> dict[str, list[tuple[str, int]]]:
    """scenario name -> [(repo path, size)] for every file under snapshots/sre."""
    from huggingface_hub import HfApi  # lazy: only this script needs it

    by_scenario: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for entry in HfApi().list_repo_tree(
        REPO_ID, repo_type="dataset", recursive=True, path_in_repo=SRE_PREFIX
    ):
        size = getattr(entry, "size", None)
        if size is None:  # directory
            continue
        parts = entry.path.split("/")
        by_scenario[parts[3]].append((entry.path, size))
    return by_scenario


def _is_small(path: str) -> bool:
    name = path.rsplit("/", 1)[1]
    return name in SMALL_FILES or "/alerts/" in path or name.startswith("alerts_in_alerting_state")


def _telemetry_paths(files: list[tuple[str, int]], local_dir: Path) -> list[tuple[str, int]]:
    """Logs + traces + service metrics for services that alerted (needs pass-1 files on disk)."""
    scenario_dir = local_dir / Path(files[0][0]).parent
    while scenario_dir.name != "" and not scenario_dir.name.startswith("Scenario-"):
        scenario_dir = scenario_dir.parent
    services = alerted_services(scenario_dir, load_ground_truth(scenario_dir))
    wanted = []
    for path, size in files:
        name = path.rsplit("/", 1)[1]
        if name in TELEMETRY_FILES:
            wanted.append((path, size))
        elif (
            "/metrics/service_" in path and name.removeprefix("service_").removesuffix("_raw.tsv") in services
        ):
            wanted.append((path, size))
    return wanted


def _download(paths: list[str], local_dir: Path, attempts: int = 3) -> None:
    from huggingface_hub import hf_hub_download

    for i, path in enumerate(paths, 1):
        print(f"  [{i}/{len(paths)}] {path}", flush=True)
        for attempt in range(1, attempts + 1):
            try:
                hf_hub_download(REPO_ID, path, repo_type="dataset", local_dir=str(local_dir))
                break
            except Exception as exc:  # network/transfer errors on multi-GB pulls are expected
                print(f"    attempt {attempt}/{attempts} failed: {exc}", flush=True)
                if attempt == attempts:
                    raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--local-dir", default="data/ITBench-Lite", type=Path)
    parser.add_argument("--scenario", action="append", help="e.g. Scenario-1 (repeatable; default: all 35)")
    parser.add_argument(
        "--with-telemetry", action="store_true", help="also fetch logs/traces/alerted metrics"
    )
    parser.add_argument(
        "--plan", action="store_true", help="print what would be fetched and its size, then exit"
    )
    args = parser.parse_args()

    by_scenario = _list_sre_files()
    scenarios = args.scenario or sorted(by_scenario, key=lambda s: int(s.split("-")[1]))
    unknown = set(scenarios) - set(by_scenario)
    if unknown:
        sys.exit(f"unknown scenario(s): {sorted(unknown)}")

    for scenario in scenarios:
        files = by_scenario[scenario]
        small = [(p, s) for p, s in files if _is_small(p)]
        todo = [p for p, _ in small if not (args.local_dir / p).exists()]
        if todo and not args.plan:
            print(f"{scenario}: fetching {len(todo)} small files")
            _download(todo, args.local_dir)
        if not args.with_telemetry:
            continue
        telemetry = _telemetry_paths(files, args.local_dir)
        missing = [(p, s) for p, s in telemetry if not (args.local_dir / p).exists()]
        size_mb = sum(s for _, s in missing) / 1e6
        print(f"{scenario}: {len(missing)} telemetry files to fetch ({size_mb:,.0f} MB)", flush=True)
        if not args.plan:
            _download([p for p, _ in missing], args.local_dir)


if __name__ == "__main__":
    main()
