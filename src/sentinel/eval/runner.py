"""Runs the grid: incidents x seeds x config -> RunRecords. Phase P4 — see blueprint §7."""

from __future__ import annotations

from sentinel.env.base import EnvAdapter
from sentinel.schemas.run import RunRecord


def run_grid(env: EnvAdapter, incident_ids: list[str], seeds: list[int], config: dict) -> list[RunRecord]:
    raise NotImplementedError("eval.runner.run_grid is Phase P4 work. See ARCHITECTURE_BLUEPRINT.md §7, §8.")
