"""Phase P1: diagnosis agents, proposal parsing, telemetry tools, context building."""

from __future__ import annotations

import json

import pytest

from sentinel.agent.base import AgentExhausted
from sentinel.agent.propose import ProposalParseError, parse_proposed_action
from sentinel.agent.react import ReActDiagnosisAgent, action_catalog
from sentinel.agent.simulated import SimulatedDiagnosisAgent
from sentinel.agent.tools import ToolError, run_tool
from sentinel.context.builder import build_context, redact
from sentinel.env.offline_adapter import OfflineEnvAdapter
from sentinel.gateway.clients import ScriptedLLMClient

FINAL = (
    'Thought: redis was briefly down; restart the pod.\nFinal Answer: {"action_type": "restart_pod", '
    '"target": "payments-api", "params": {"namespace": "prod", "pod_name": "payments-api-7d9f-xk2z"}, '
    '"rationale": "transient dependency failure", "predicted_effect": "pod starts cleanly"}'
)


@pytest.fixture(scope="module")
def env() -> OfflineEnvAdapter:
    return OfflineEnvAdapter()


@pytest.fixture
def incident(env):
    return env.get_incident("pod-crashloop")


# -- propose.py ---------------------------------------------------------------------------------


def test_parse_final_answer():
    action = parse_proposed_action(FINAL)
    assert action.action_type == "restart_pod"
    assert action.params["pod_name"] == "payments-api-7d9f-xk2z"


def test_parse_rejects_missing_fields():
    with pytest.raises(ProposalParseError, match="rationale"):
        parse_proposed_action(
            'Final Answer: {"action_type": "restart_pod", "target": "x", "predicted_effect": "e"}'
        )


def test_parse_rejects_no_json():
    with pytest.raises(ProposalParseError):
        parse_proposed_action("Final Answer: restart the pod please")


# -- context / tools ----------------------------------------------------------------------------


def test_context_never_contains_fault_family(env):
    for incident_id in env.list_incidents():
        incident = env.get_incident(incident_id)
        context = build_context(incident)
        assert "fault_family" not in context
        assert len(context) // 4 <= incident.budget_tokens * 1.1


def test_context_signal_ablation(incident):
    logs_only = build_context(incident, {"logs"})
    assert "## Logs" in logs_only and "## Metrics" not in logs_only and "## Topology" not in logs_only
    with pytest.raises(ValueError):
        build_context(incident, {"logs", "vibes"})


def test_redaction():
    assert (
        redact("mail reed@example.com from 10.1.2.3 password=hunter2")
        == "mail <email> from <ip> password=<redacted>"
    )


def test_tools(incident):
    assert "redis-cache" in run_tool(incident, "get_logs", {"query": "redis"})
    assert "pod_restart_count" in run_tool(incident, "get_metrics", {"names": ["pod_restart_count"]})
    with pytest.raises(ToolError):
        run_tool(incident, "delete_everything", {})
    with pytest.raises(ToolError):  # ablated signal -> tool unavailable
        run_tool(incident, "get_traces", {}, signals={"logs"})


# -- ReAct agent ---------------------------------------------------------------------------------


def test_react_agent_calls_tools_then_proposes(incident):
    llm = ScriptedLLMClient(
        [
            'Thought: check logs.\nAction: get_logs\nAction Input: {"query": "FATAL"}',
            FINAL,
        ]
    )
    agent = ReActDiagnosisAgent(llm, max_tool_calls=4)
    action = agent.propose(incident)
    assert action.action_type == "restart_pod"
    assert len(llm.requests) == 2
    observation = llm.requests[1]["messages"][-1]["content"]
    assert observation.startswith("Observation:") and "connection refused" in observation
    assert agent.usage.calls == 2 and agent.usage.total_tokens > 0


@pytest.mark.parametrize("incident_id", ["pod-crashloop", "memory-leak-oom", "itbench-sre-scenario-4"])
def test_react_agent_prompt_never_leaks_ground_truth(env, incident_id):
    incident = env.get_incident(incident_id)
    llm = ScriptedLLMClient([FINAL])
    ReActDiagnosisAgent(llm).propose(incident)
    sent = json.dumps(llm.requests[0])
    # P0 ids name their fault ("pod-crashloop"), so the id itself must never reach the agent.
    assert incident_id not in sent
    # fault_family labels like "memory_leak" / "feature_flag_fault" are eval-only vocabulary.
    assert incident.fault_family not in sent
    assert "oracle" not in sent and "labeled_actions" not in sent and "root_cause" not in sent


def test_react_agent_recovers_from_bad_turns(incident):
    llm = ScriptedLLMClient(
        [
            "I think it is redis.",  # neither action nor final answer
            "Action: nope\nAction Input: {}",  # unknown tool
            'Final Answer: {"action_type": "restart_pod"}',  # invalid proposal
            FINAL,
        ]
    )
    action = ReActDiagnosisAgent(llm, max_tool_calls=6).propose(incident)
    assert action.target == "payments-api"
    feedback = [m["content"] for m in llm.requests[-1]["messages"] if m["role"] == "user"][1:]
    assert any("unknown or unavailable tool" in f for f in feedback)
    assert any("not a valid ProposedAction" in f for f in feedback)


def test_react_agent_feedback_continues_same_conversation(incident):
    llm = ScriptedLLMClient([FINAL, FINAL])
    agent = ReActDiagnosisAgent(llm)
    agent.propose(incident)
    agent.incorporate_feedback(incident, ["judge: restarting does not fix a redis outage"])
    last_user = [m for m in llm.requests[1]["messages"] if m["role"] == "user"][-1]["content"]
    assert "restarting does not fix a redis outage" in last_user


def test_react_agent_gives_up_after_budget(incident):
    llm = ScriptedLLMClient(["Action: get_traces\nAction Input: {}"] * 3 + ["still thinking"])
    with pytest.raises(AgentExhausted):
        ReActDiagnosisAgent(llm, max_tool_calls=3).propose(incident)


def test_action_catalog_lists_envelope_types():
    catalog = action_catalog()
    assert "restart_pod" in catalog and "remove_fault_injection" in catalog


# -- simulated agent -----------------------------------------------------------------------------


def test_simulated_agent_is_deterministic_per_seed(env, incident):
    a = SimulatedDiagnosisAgent(env.labeled_actions, seed=7).propose(incident)
    b = SimulatedDiagnosisAgent(env.labeled_actions, seed=7).propose(incident)
    assert a == b


def test_simulated_agent_rationale_is_label_independent(env, incident):
    agent = SimulatedDiagnosisAgent(
        env.labeled_actions,
        seed=0,
        label_mix={"correct": 1, "ineffective": 1, "destructive": 1, "out_of_envelope": 1},
    )
    actions = [agent.propose(incident)] + [agent.incorporate_feedback(incident, []) for _ in range(3)]
    for action in actions:
        text = (action.rationale + action.predicted_effect).lower()
        for leak in ("correct", "destructive", "ineffective", "out_of_envelope", "label", "unsafe"):
            assert leak not in text


def test_simulated_agent_never_repeats_and_then_exhausts(env, incident):
    agent = SimulatedDiagnosisAgent(env.labeled_actions, seed=1)
    seen = {agent.propose(incident).model_dump_json()}
    for _ in range(len(env.labeled_actions("pod-crashloop")) - 1):
        seen.add(agent.incorporate_feedback(incident, ["no"]).model_dump_json())
    assert len(seen) == len(env.labeled_actions("pod-crashloop"))
    with pytest.raises(AgentExhausted):
        agent.incorporate_feedback(incident, ["no"])


def test_simulated_agent_label_mix_is_respected(env, incident):
    only_destructive = {"correct": 0, "ineffective": 0, "destructive": 1, "out_of_envelope": 0}
    action = SimulatedDiagnosisAgent(env.labeled_actions, label_mix=only_destructive).propose(incident)
    assert env.ground_truth_action_safe(action, "pod-crashloop") is False
