"""Orchestrator loop — Phase P2. Not implemented yet; see PROGRESS.md.

Pseudocode from blueprint §5:
    for step in range(max_steps):
        action = agent.propose(context)
        verdict = verifier.verify(incident, action)
        if verdict.decision == "allow":
            result = executor.run(action, dry_run=config.dry_run)
            if env.evaluate(incident_id): break        # resolved
        elif verdict.decision == "revise":
            context = agent.incorporate_feedback(verdict.reasons)   # closed-loop, TRIAD-style
        else:  # block
            escalate_to_human(); break
    record_step(...)

Every step must be recorded as a StepRecord and every run as a RunRecord (store/duckdb_store.py) --
per CLAUDE.md, "no experiment result exists unless it's a RunRecord row in DuckDB."
"""

from __future__ import annotations

from sentinel.agent.react import DiagnosisAgent
from sentinel.env.base import EnvAdapter
from sentinel.executor.executor import Executor
from sentinel.schemas.run import RunRecord
from sentinel.verifier.base import Verifier


class Orchestrator:
    def __init__(
        self,
        env: EnvAdapter,
        agent: DiagnosisAgent,
        verifier: Verifier,
        executor: Executor,
        *,
        max_steps: int = 6,
    ) -> None:
        self._env = env
        self._agent = agent
        self._verifier = verifier
        self._executor = executor
        self._max_steps = max_steps

    def run(self, incident_id: str, *, seed: int = 0, dry_run: bool = True) -> RunRecord:
        raise NotImplementedError(
            "orchestrator.loop.Orchestrator.run is Phase P2 work. See ARCHITECTURE_BLUEPRINT.md §5, §8."
        )
