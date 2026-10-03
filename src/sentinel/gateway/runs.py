"""Live console runs (FRONTEND_BLUEPRINT.md §5.2): the orchestrator runs in a background thread and
each StepRecord is appended to the run's event log AS THE LOOP PRODUCES IT; the SSE endpoint replays
that log and then waits for new events. A client that reconnects mid-run gets every event from the
start -- the log is the source, not a one-shot queue.

Each run gets its own OfflineEnvAdapter: the adapter tracks the "live" incident, so concurrent console
runs on a shared instance would race. Finished runs are written to DuckDB (experiment "console").
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

from sentinel.config import config_hash
from sentinel.env.offline_adapter import OfflineEnvAdapter
from sentinel.observability.metrics import SentinelMetrics, record_run, record_step
from sentinel.orchestrator.factory import build_orchestrator
from sentinel.schemas.run import RunRecord, StepRecord
from sentinel.store.duckdb_store import DuckDBStore
from sentinel.verifier.base import Verifier

CONSOLE_EXPERIMENT = "console"


@dataclass
class RunHandle:
    run_id: str
    incident_id: str
    variant: str
    tau: float
    dry_run: bool
    events: list[tuple[str, object]] = field(
        default_factory=list
    )  # ("step", StepRecord) | ("final", RunRecord) | ("error", str)
    cond: threading.Condition = field(default_factory=threading.Condition)

    def push(self, kind: str, payload: object) -> None:
        with self.cond:
            self.events.append((kind, payload))
            self.cond.notify_all()

    def wait_for(self, index: int, timeout: float) -> tuple[str, object] | None:
        """The event at `index`, waiting up to `timeout` seconds for it to exist."""
        with self.cond:
            self.cond.wait_for(lambda: len(self.events) > index, timeout=timeout)
            return self.events[index] if len(self.events) > index else None

    @property
    def done(self) -> bool:
        return any(kind in ("final", "error") for kind, _ in self.events)

    @property
    def final(self) -> RunRecord | None:
        return next((p for k, p in self.events if k == "final"), None)  # type: ignore[return-value]


class RunManager:
    def __init__(
        self, config: dict, store: DuckDBStore, metrics: SentinelMetrics, learned_loader=None
    ) -> None:
        self._config = config
        self._store = store
        self._metrics = metrics
        self._learned_loader = learned_loader
        self._learned: Verifier | None = None
        self._handles: dict[str, RunHandle] = {}
        self._lock = threading.Lock()

    def get(self, run_id: str) -> RunHandle | None:
        return self._handles.get(run_id)

    def _learned_verifier(self, variant: str) -> Verifier | None:
        if variant not in ("learned", "combined"):
            return None
        with self._lock:
            if self._learned is None:
                self._learned = self._learned_loader()  # raises FileNotFoundError -> 409 in the API
        return self._learned

    def start(self, incident_id: str, variant: str, tau: float, dry_run: bool) -> RunHandle:
        learned = self._learned_verifier(variant)  # fail fast, before a thread exists
        handle = RunHandle(uuid.uuid4().hex[:12], incident_id, variant, tau, dry_run)
        self._handles[handle.run_id] = handle
        threading.Thread(target=self._execute, args=(handle, learned), daemon=True).start()
        return handle

    def _execute(self, handle: RunHandle, learned: Verifier | None) -> None:
        delay = self._config.get("gateway", {}).get("step_delay_ms", 0) / 1000

        def on_step(step: StepRecord) -> None:
            record_step(self._metrics, step, handle.variant)
            handle.push("step", step)
            time.sleep(delay)  # display pacing only -- the run itself is already decided

        try:
            env = OfflineEnvAdapter()
            orchestrator = build_orchestrator(
                self._config, env, variant=handle.variant, tau=handle.tau, learned=learned
            )
            run = orchestrator.run(handle.incident_id, dry_run=handle.dry_run, on_step=on_step)
            self._store.write_run(
                run,
                run_id=handle.run_id,
                meta={
                    "experiment": CONSOLE_EXPERIMENT,
                    "variant": handle.variant,
                    "tau": handle.tau,
                    "agent_kind": self._config["agent"]["kind"],
                    "dry_run": handle.dry_run,
                    "cell_config_hash": config_hash(self._config),
                },
            )
            record_run(self._metrics, run, handle.variant)
            handle.push("final", run)
        except Exception as exc:  # surfaced to the console as an SSE error event
            handle.push("error", f"{type(exc).__name__}: {exc}")
