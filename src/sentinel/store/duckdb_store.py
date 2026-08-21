"""DuckDB-backed RunRecord/StepRecord store — Phase P2. Not implemented yet; see PROGRESS.md.

Per CLAUDE.md: "no experiment result exists unless it's a RunRecord row in DuckDB." config/
default.yaml's store.path sets the DuckDB file location.
"""

from __future__ import annotations

from pathlib import Path

from sentinel.schemas.run import RunRecord


class DuckDBStore:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def write_run(self, run: RunRecord) -> None:
        raise NotImplementedError(
            "store.duckdb_store.DuckDBStore.write_run is Phase P2 work. See ARCHITECTURE_BLUEPRINT.md §5, §8."
        )

    def read_runs(self, *, incident_id: str | None = None) -> list[RunRecord]:
        raise NotImplementedError(
            "store.duckdb_store.DuckDBStore.read_runs is Phase P2 work. See ARCHITECTURE_BLUEPRINT.md §5, §8."
        )
