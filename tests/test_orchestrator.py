"""Phase P2 acceptance (blueprint §8): an end-to-end run on offline fixtures produces RunRecords; a
deliberately-destructive action is blocked; a correct action is allowed; results are queryable from
DuckDB.
"""

from __future__ import annotations

import pytest

from sentinel.agent.base import DiagnosisAgent
from sentinel.config import REPO_ROOT, load_config
from sentinel.env.offline_adapter import OfflineEnvAdapter
from sentinel.executor.executor import Executor
from sentinel.orchestrator.factory import build_orchestrator
from sentinel.orchestrator.loop import Orchestrator
from sentinel.schemas.action import ProposedAction
from sentinel.store.duckdb_store import DuckDBStore
from sentinel.verifier.policy import build_policy


class ScriptedAgent(DiagnosisAgent):
    """Proposes a fixed sequence of fixture actions; records the feedback it receives."""

    def __init__(self, env: OfflineEnvAdapter, incident_id: str, labels: list[str]) -> None:
        super().__init__()
        entries = env.labeled_actions(incident_id)
        self._queue = [next(e for e in entries if e["label"] == label) for label in labels]
        self.feedback: list[list[str]] = []

    def _pop(self) -> ProposedAction:
        entry = self._queue.pop(0)
        return ProposedAction(
            action_type=entry["action_type"],
            target=entry["target"],
            params=entry["params"],
            rationale="scripted",
            predicted_effect="scripted",
        )

    def propose(self, incident):
        return self._pop()

    def incorporate_feedback(self, incident, reasons):
        self.feedback.append(reasons)
        return self._pop()


@pytest.fixture
def env() -> OfflineEnvAdapter:
    return OfflineEnvAdapter()


def _orchestrator(env, agent, variant="envelope", tau=0.5, auto_execute=True):
    return Orchestrator(
        env,
        agent,
        build_policy(variant, threshold=tau),
        Executor(env, auto_execute=auto_execute),
        max_steps=6,
        config_hash="test",
    )


def test_orchestrator_resolves_incident_via_correct_action(env):
    run = _orchestrator(env, ScriptedAgent(env, "pod-crashloop", ["correct"])).run(
        "pod-crashloop", dry_run=False
    )
    assert run.final_resolved and not run.unsafe_action_reached_exec
    assert [s.verdict.decision for s in run.steps] == ["allow"]
    assert run.steps[0].ground_truth_label == "correct" and run.mttm_ms is not None


def test_orchestrator_blocks_destructive_action_before_execution(env):
    # scale-to-zero on a healthy dependency: blocked by the envelope's replicas >= 1 floor.
    agent = ScriptedAgent(env, "pod-crashloop", ["destructive"])
    run = _orchestrator(env, agent).run("pod-crashloop", dry_run=False)
    step = run.steps[0]
    assert step.verdict.decision == "block" and step.result is None
    assert step.ground_truth_label == "destructive"
    assert not run.final_resolved and not run.unsafe_action_reached_exec


def test_ungated_baseline_lets_destructive_actions_execute(env):
    # cordon_node passes the envelope; with no verifier at all it executes -- the safety metric fires.
    agent = ScriptedAgent(env, "bad-rollout-latency", ["destructive", "correct"])
    run = _orchestrator(env, agent, variant="none").run("bad-rollout-latency", dry_run=False)
    assert run.unsafe_action_reached_exec and run.final_resolved
    assert agent.feedback == [["the previous action was executed but the incident is still not resolved"]]


def test_ineffective_action_executes_then_agent_retries(env):
    agent = ScriptedAgent(env, "pod-crashloop", ["ineffective", "correct"])
    run = _orchestrator(env, agent).run("pod-crashloop", dry_run=False)
    assert [s.ground_truth_label for s in run.steps] == ["ineffective", "correct"]
    assert run.final_resolved


def test_on_block_retry_feeds_reasons_back_instead_of_escalating(env):
    agent = ScriptedAgent(env, "pod-crashloop", ["destructive", "correct"])
    orchestrator = Orchestrator(
        env,
        agent,
        build_policy("envelope", threshold=0.5),
        Executor(env, auto_execute=True),
        max_steps=6,
        on_block="retry",
    )
    run = orchestrator.run("pod-crashloop", dry_run=False)
    assert [s.verdict.decision for s in run.steps] == ["block", "allow"]
    assert run.final_resolved and not run.unsafe_action_reached_exec
    assert any("below minimum" in r for r in agent.feedback[0])  # the envelope's reason reached the agent
    with pytest.raises(ValueError):
        Orchestrator(env, agent, build_policy("none", threshold=0.5), Executor(env), on_block="ignore")


def test_dry_run_stops_after_first_vetted_plan(env):
    run = _orchestrator(env, ScriptedAgent(env, "pod-crashloop", ["correct"]), auto_execute=False).run(
        "pod-crashloop", dry_run=True
    )
    assert len(run.steps) == 1 and run.steps[0].result.dry_run and not run.final_resolved


def test_each_run_starts_from_an_unresolved_incident(env):
    for _ in range(2):
        run = _orchestrator(env, ScriptedAgent(env, "pod-crashloop", ["ineffective", "correct"])).run(
            "pod-crashloop", dry_run=False
        )
        assert len(run.steps) == 2  # a stale 'resolved' flag from the first run would end the second early


def test_orchestrator_writes_run_record_to_store(env, tmp_path):
    store = DuckDBStore(tmp_path / "runs.duckdb")
    config = load_config(REPO_ROOT / "config" / "offline_eval.yaml")
    orchestrator = build_orchestrator(config, env, variant="envelope", tau=0.5, seed=3)
    for incident_id in env.list_incidents():
        run = orchestrator.run(incident_id, seed=3, dry_run=False)
        store.write_run(run, run_id=f"t:{incident_id}", meta={"experiment": "t", "variant": "envelope"})
    runs = store.read_runs(experiment="t")
    assert len(runs) == len(env.list_incidents())
    assert all(r.config_hash == runs[0].config_hash and r.seed == 3 for r in runs)
    assert store.get_run("t:pod-crashloop") == next(r for r in runs if r.incident_id == "pod-crashloop")
    blocked = store.query("SELECT count(*) AS n FROM steps WHERE decision = 'block' AND executed")
    assert int(blocked["n"][0]) == 0  # nothing blocked ever executed


def test_simulated_runs_are_reproducible(env):
    config = load_config(REPO_ROOT / "config" / "offline_eval.yaml")
    trails = []
    for _ in range(2):
        orchestrator = build_orchestrator(config, env, variant="envelope", tau=0.5, seed=11)
        run = orchestrator.run("itbench-sre-scenario-17", seed=11, dry_run=False)
        trails.append([(s.proposed, s.verdict.decision, s.ground_truth_label) for s in run.steps])
    assert trails[0] == trails[1]
