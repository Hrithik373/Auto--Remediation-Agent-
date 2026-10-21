# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# The Orchestrator.run loop: asks the agent, verifies, then executes, revises or escalates.
# Records every step as a StepRecord and returns the whole run as a RunRecord.
"""Orchestrator loop (blueprint §5): diagnose -> propose -> VERIFY -> act / revise / escalate.

    for step in range(max_steps):
        action  = agent.propose(...) | agent.incorporate_feedback(...)
        verdict = verifier.verify(incident, action)
        allow   -> executor.run(action, verdict=verdict, dry_run=...)   # the ONLY path to apply
                   resolved? done.  dry run? done (a plan was produced).  else feed back and retry.
        revise  -> agent.incorporate_feedback(verdict.reasons)          # closed loop
        block   -> escalate to a human; stop.

Every step becomes a StepRecord and every run a RunRecord (CLAUDE.md: no result exists unless it is
a RunRecord row in DuckDB). The ground-truth label is attached to a step AFTER its verdict is final,
from the env oracle -- it never flows back into the agent or the verifier.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from sentinel.agent.base import AgentExhausted, DiagnosisAgent
from sentinel.env.base import EnvAdapter
from sentinel.executor.executor import Executor
from sentinel.labeling.oracle_labeler import derive_label
from sentinel.schemas.action import ProposedAction
from sentinel.schemas.incident import IncidentContext
from sentinel.schemas.run import RunRecord, StepRecord
from sentinel.verifier.base import Verifier

StepCallback = Callable[[StepRecord], None]
NOT_RESOLVED_FEEDBACK = "the previous action was executed but the incident is still not resolved"


def _verifier_usage(verifier: Verifier) -> tuple[int, float]:
    totals = getattr(verifier, "usage_totals", None)
    if totals is not None:
        return totals()
    ledger = getattr(verifier, "usage", None)
    return (ledger.total_tokens, ledger.cost_usd) if ledger is not None else (0, 0.0)


class Orchestrator:
    def __init__(
        self,
        env: EnvAdapter,
        agent: DiagnosisAgent,
        verifier: Verifier,
        executor: Executor,
        *,
        max_steps: int = 6,
        config_hash: str = "unhashed",
        on_block: str = "escalate",
    ) -> None:
        if on_block not in ("escalate", "retry"):
            raise ValueError(f"on_block must be 'escalate' or 'retry', got {on_block!r}")
        self._env = env
        self._agent = agent
        self._verifier = verifier
        self._executor = executor
        self._max_steps = max_steps
        self._config_hash = config_hash
        # escalate (blueprint §5 default): a blocked proposal ends the run and pages a human.
        # retry: the block reasons go back to the agent like a revise; escalation happens only when
        # the agent runs out of proposals or steps. An eval ablation compares the two.
        self._on_block = on_block

    def _usage(self) -> tuple[int, float]:
        tokens, cost = _verifier_usage(self._verifier)
        return self._agent.usage.total_tokens + tokens, self._agent.usage.cost_usd + cost

    def _next_action(self, incident: IncidentContext, feedback: list[str] | None) -> ProposedAction | None:
        try:
            if feedback is None:
                return self._agent.propose(incident)
            return self._agent.incorporate_feedback(incident, feedback)
        except AgentExhausted:
            return None  # nothing left to try -> the run escalates

    def run(
        self, incident_id: str, *, seed: int = 0, dry_run: bool = True, on_step: StepCallback | None = None
    ) -> RunRecord:
        self._env.reset(incident_id)
        incident = self._env.get_incident(incident_id)
        start = time.perf_counter()
        start_tokens, start_cost = self._usage()
        steps: list[StepRecord] = []
        feedback: list[str] | None = None
        resolved = unsafe_exec = False

        for step_idx in range(self._max_steps):
            t0, (tok0, _) = time.perf_counter(), self._usage()
            action = self._next_action(incident, feedback)
            if action is None:
                break
            verdict = self._verifier.verify(incident, action)
            label = derive_label(self._env, action, incident_id)  # eval-only, after the verdict
            result = None
            if verdict.decision == "allow":
                result = self._executor.run(action, verdict=verdict, dry_run=dry_run)
                unsafe_exec |= bool(result.executed and not result.dry_run and label == "destructive")
                resolved = bool(result.executed and self._env.evaluate(incident_id))
            step = StepRecord(
                step_idx=step_idx,
                proposed=action,
                verdict=verdict,
                result=result,
                tokens=self._usage()[0] - tok0,
                latency_ms=(time.perf_counter() - t0) * 1000,
                ground_truth_label=label,
            )
            steps.append(step)
            if on_step is not None:
                on_step(step)
            escalate = verdict.decision == "block" and self._on_block == "escalate"
            if escalate or resolved or (verdict.decision == "allow" and dry_run):
                break  # escalated, fixed, or (dry run) a vetted plan exists -- nothing more to do
            feedback = verdict.reasons if verdict.decision != "allow" else [NOT_RESOLVED_FEEDBACK]

        tokens, cost = self._usage()
        return RunRecord(
            incident_id=incident_id,
            seed=seed,
            config_hash=self._config_hash,
            steps=steps,
            final_resolved=resolved,
            unsafe_action_reached_exec=unsafe_exec,
            mttm_ms=(time.perf_counter() - start) * 1000 if resolved else None,
            total_tokens=tokens - start_tokens,
            total_cost_usd=round(cost - start_cost, 8),
        )
