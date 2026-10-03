"""DuckDB-backed RunRecord/StepRecord store (blueprint §2, §5).

CLAUDE.md: "no experiment result exists unless it's a RunRecord row in DuckDB." Each run is one row in
`runs` (+ its N rows in `steps`). The full RunRecord JSON is kept for lossless round-trips; the flat
columns exist for SQL in the eval harness and the console API.

Connections are opened per operation, so readers (gateway) and writers (eval) don't hold a lock.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from sentinel.schemas.run import RunRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id VARCHAR PRIMARY KEY,
    created_at TIMESTAMP,
    experiment VARCHAR,
    variant VARCHAR,
    agent_kind VARCHAR,
    tau DOUBLE,
    incident_id VARCHAR,
    seed INTEGER,
    config_hash VARCHAR,
    final_resolved BOOLEAN,
    unsafe_action_reached_exec BOOLEAN,
    mttm_ms DOUBLE,
    total_tokens BIGINT,
    total_cost_usd DOUBLE,
    n_steps INTEGER,
    meta_json VARCHAR,
    record_json VARCHAR
);
CREATE TABLE IF NOT EXISTS steps (
    run_id VARCHAR,
    step_idx INTEGER,
    action_type VARCHAR,
    target VARCHAR,
    decision VARCHAR,
    risk_score DOUBLE,
    ground_truth_label VARCHAR,
    envelope_decision VARCHAR,
    judge_decision VARCHAR,
    learned_decision VARCHAR,
    executed BOOLEAN,
    resolved BOOLEAN,
    tokens BIGINT,
    latency_ms DOUBLE
);
"""


class DuckDBStore:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute(_SCHEMA)

    @property
    def path(self) -> Path:
        return self._db_path

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self._db_path))

    def write_run(self, run: RunRecord, *, run_id: str | None = None, meta: dict | None = None) -> str:
        """Insert (or replace, by run_id) one run and its steps. Returns the run_id."""
        run_id = run_id or uuid.uuid4().hex
        meta = meta or {}
        with self._connect() as con:
            con.execute("BEGIN")
            con.execute("DELETE FROM steps WHERE run_id = ?", [run_id])
            con.execute("DELETE FROM runs WHERE run_id = ?", [run_id])
            con.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    run_id,
                    datetime.now(UTC).replace(tzinfo=None),
                    meta.get("experiment"),
                    meta.get("variant"),
                    meta.get("agent_kind"),
                    meta.get("tau"),
                    run.incident_id,
                    run.seed,
                    run.config_hash,
                    run.final_resolved,
                    run.unsafe_action_reached_exec,
                    run.mttm_ms,
                    run.total_tokens,
                    run.total_cost_usd,
                    len(run.steps),
                    json.dumps(meta, sort_keys=True, default=str),
                    run.model_dump_json(),
                ],
            )
            if run.steps:
                con.executemany(
                    "INSERT INTO steps VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [_step_row(run_id, step) for step in run.steps],
                )
            con.execute("COMMIT")
        return run_id

    def write_runs(self, batch: list[tuple[str, RunRecord, dict]]) -> None:
        """Bulk insert-or-replace of (run_id, run, meta) in one transaction (the eval grid is thousands)."""
        if not batch:
            return
        now = datetime.now(UTC).replace(tzinfo=None)
        run_rows, step_rows, ids = [], [], []
        for run_id, run, meta in batch:
            ids.append(run_id)
            run_rows.append(
                [
                    run_id,
                    now,
                    meta.get("experiment"),
                    meta.get("variant"),
                    meta.get("agent_kind"),
                    meta.get("tau"),
                    run.incident_id,
                    run.seed,
                    run.config_hash,
                    run.final_resolved,
                    run.unsafe_action_reached_exec,
                    run.mttm_ms,
                    run.total_tokens,
                    run.total_cost_usd,
                    len(run.steps),
                    json.dumps(meta, sort_keys=True, default=str),
                    run.model_dump_json(),
                ]
            )
            step_rows.extend(_step_row(run_id, step) for step in run.steps)
        with self._connect() as con:
            con.execute("BEGIN")
            con.executemany("DELETE FROM steps WHERE run_id = ?", [[i] for i in ids])
            con.executemany("DELETE FROM runs WHERE run_id = ?", [[i] for i in ids])
            con.executemany(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", run_rows
            )
            if step_rows:
                con.executemany(
                    "INSERT INTO steps VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", step_rows
                )
            con.execute("COMMIT")

    def delete_experiment(self, experiment: str) -> int:
        with self._connect() as con:
            ids = [
                r[0]
                for r in con.execute("SELECT run_id FROM runs WHERE experiment = ?", [experiment]).fetchall()
            ]
            con.execute(
                "DELETE FROM steps WHERE run_id IN (SELECT run_id FROM runs WHERE experiment = ?)",
                [experiment],
            )
            con.execute("DELETE FROM runs WHERE experiment = ?", [experiment])
        return len(ids)

    def read_runs_with_meta(self, experiment: str) -> list[tuple[dict, RunRecord]]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT meta_json, record_json FROM runs WHERE experiment = ? ORDER BY run_id", [experiment]
            ).fetchall()
        return [(json.loads(meta), RunRecord.model_validate_json(record)) for meta, record in rows]

    def read_runs(self, *, incident_id: str | None = None, experiment: str | None = None) -> list[RunRecord]:
        return [run for _, run in self.read_runs_with_ids(incident_id=incident_id, experiment=experiment)]

    def read_runs_with_ids(
        self, *, incident_id: str | None = None, experiment: str | None = None
    ) -> list[tuple[str, RunRecord]]:
        clauses, params = [], []
        if incident_id is not None:
            clauses.append("incident_id = ?")
            params.append(incident_id)
        if experiment is not None:
            clauses.append("experiment = ?")
            params.append(experiment)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as con:
            rows = con.execute(
                f"SELECT run_id, record_json FROM runs {where} ORDER BY created_at, run_id", params
            ).fetchall()
        return [(run_id, RunRecord.model_validate_json(record)) for run_id, record in rows]

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._connect() as con:
            row = con.execute("SELECT record_json FROM runs WHERE run_id = ?", [run_id]).fetchone()
        return RunRecord.model_validate_json(row[0]) if row else None

    def query(self, sql: str, params: list | None = None):
        """Read-only SQL for the eval harness; returns a pandas DataFrame."""
        with self._connect() as con:
            return con.execute(sql, params or []).df()


def _step_row(run_id: str, step) -> list:
    layers = {layer.verifier: layer.decision for layer in step.verdict.layers}
    result = step.result
    return [
        run_id,
        step.step_idx,
        step.proposed.action_type,
        step.proposed.target,
        step.verdict.decision,
        step.verdict.risk_score,
        step.ground_truth_label,
        layers.get("envelope"),
        layers.get("llm_judge"),
        layers.get("learned"),
        bool(result and result.executed),
        bool(result and result.resolved),
        step.tokens,
        step.latency_ms,
    ]
