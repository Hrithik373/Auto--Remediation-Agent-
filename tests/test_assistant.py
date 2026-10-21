"""Phase P6: sentinel-assistant -- explanations, scenario judgements, offline routing, LLM loop, API.

The assistant must never decide (verdicts come from verifier.policy) and never execute (no executor
reference, no apply_action call). Both are tested here, not just documented.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import joblib
import pytest
import yaml
from fastapi.testclient import TestClient

from sentinel.assistant.entities import incident_entities
from sentinel.assistant.explain import assess, explain_verdict
from sentinel.assistant.knowledge import KnowledgeBase
from sentinel.assistant.loop import ToolLoop
from sentinel.assistant.prompts import SYSTEM_TEMPLATE
from sentinel.assistant.scenarios import ScenarioEvaluator, UnknownIncident
from sentinel.assistant.service import REPO_ROOT, AssistantService, build_assistant
from sentinel.config import load_config
from sentinel.env.offline_adapter import OfflineEnvAdapter
from sentinel.gateway import api, assistant_api
from sentinel.gateway.app import app
from sentinel.gateway.clients import ScriptedLLMClient
from sentinel.labeling.dataset import build_dataset
from sentinel.schemas.assistant import ChatMessage, ChatRequest, ScenarioRequest
from sentinel.schemas.run import RunRecord, StepRecord
from sentinel.schemas.verdict import LayerVerdict, Verdict
from sentinel.verifier.learned import LearnedVerifier, train_bundle
from sentinel.verifier.llm_judge import JUDGE_SYSTEM

ASSISTANT_PKG = REPO_ROOT / "src" / "sentinel" / "assistant"


def _layers(env="allow", env_risk=0.35, judge=None, learned=None, env_reasons=None):
    def layer(name, spec):
        if spec is None:
            return LayerVerdict(verifier=name, decision="skipped", reasons=["layer not active for this run"])
        decision, risk, reasons = spec
        return LayerVerdict(verifier=name, decision=decision, risk_score=risk, reasons=reasons)

    return [
        LayerVerdict(verifier="envelope", decision=env, risk_score=env_risk, reasons=env_reasons or ["ok"]),
        layer("llm_judge", judge),
        layer("learned", learned),
    ]


def _verdict(decision, risk, layers):
    return Verdict(decision=decision, risk_score=risk, reasons=["r"], verifier="combined", layers=layers)


# -- explain.py ------------------------------------------------------------------------------------


def test_explain_envelope_block_is_final_and_tau_cannot_change_it():
    layers = _layers(
        env="block", env_risk=1.0, env_reasons=["action_type 'drain_node' is not in the allow-list"]
    )
    layers[2] = LayerVerdict(
        verifier="learned", decision="skipped", reasons=["not evaluated: the envelope already blocked"]
    )
    e = explain_verdict(_verdict("block", 1.0, layers), tau=0.5)
    assert e.decided_by == "envelope" and e.headline.startswith("BLOCKED by the envelope")
    assert "drain_node" in e.headline
    assert "hard gate" in e.threshold_note
    assert e.counterfactuals[0].description.startswith("No value of τ")
    assert "already blocked" in e.layers[2].summary
    assert [layer.verifier for layer in e.layers] == ["envelope", "llm_judge", "learned"]  # always all three


def test_explain_allow_names_the_closest_layer_and_the_flip_threshold():
    v = _verdict("allow", 0.31, _layers(judge=("allow", 0.12, ["fine"]), learned=("allow", 0.31, ["x"])))
    e = explain_verdict(v, tau=0.5)
    assert e.decision == "allow" and e.decided_by == "learned"
    assert "0.31" in e.headline and "below τ=0.50" in e.headline
    assert e.layers[1].over_threshold is False and e.layers[2].over_threshold is False
    assert e.counterfactuals[0].decision == "block" and "0.31" in e.counterfactuals[0].description


def test_explain_block_over_tau_and_revise():
    block = explain_verdict(
        _verdict("block", 0.9, _layers(learned=("block", 0.9, ["P(destructive) = 0.90"]))), 0.5
    )
    assert block.decided_by == "learned" and block.headline.startswith("BLOCKED")
    assert block.layers[2].over_threshold is True
    assert block.counterfactuals[0].decision == "allow" and "0.90" in block.counterfactuals[0].description

    revise = explain_verdict(_verdict("revise", 0.7, _layers(judge=("revise", 0.7, ["wrong target"]))), 0.5)
    assert revise.decided_by == "llm_judge" and revise.headline.startswith("SENT BACK FOR REVISION")


def test_explain_fail_closed_judge_is_described_as_unavailable_not_dangerous():
    v = _verdict(
        "block", 1.0, _layers(judge=("block", 1.0, ["fail-closed: judge unavailable (RuntimeError)"]))
    )
    e = explain_verdict(v, 0.5)
    assert "failed closed" in e.layers[1].summary
    assert "No τ allows a risk of 1.00" in e.counterfactuals[0].description


def test_explain_ungated_and_single_layer_verdicts():
    ungated = _verdict(
        "allow",
        0.0,
        [
            LayerVerdict(verifier=n, decision="skipped", reasons=["layer not active for this run"])
            for n in ("envelope", "llm_judge", "learned")
        ],
    )
    e = explain_verdict(ungated, 0.5)
    assert e.decided_by == "none" and "ungated" in e.headline and e.counterfactuals == []

    single = Verdict(decision="allow", risk_score=0.1, reasons=["ok"], verifier="envelope")
    assert explain_verdict(single, 0.5).decided_by == "envelope"


@pytest.mark.parametrize(
    ("label", "decision", "kind"),
    [
        ("destructive", "block", "correct_catch"),
        ("destructive", "allow", "missed"),
        ("out_of_envelope", "block", "correct_catch"),
        ("correct", "allow", "correct_allow"),
        ("correct", "revise", "false_block"),
        ("ineffective", "allow", "harmless_allowed"),
        ("ineffective", "block", "harmless_blocked"),
        (None, "allow", "unknown"),
    ],
)
def test_ground_truth_assessment_uses_the_eval_terms(label, decision, kind):
    assert assess(label, decision, "fixture").assessment == kind


# -- scenarios.py ----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def model_path(tmp_path_factory):
    env = OfflineEnvAdapter()
    bundle = train_bundle(
        build_dataset(env), {i: env.get_incident(i) for i in env.list_incidents()}, n_folds=3
    )
    path = tmp_path_factory.mktemp("models") / "learned_verifier.joblib"
    joblib.dump(bundle, path)
    return path


class NoApplyEnv(OfflineEnvAdapter):
    def apply_action(self, action, dry_run=True):  # noqa: ARG002
        raise AssertionError("the assistant must never apply an action")


@pytest.fixture(scope="module")
def evaluator(model_path):
    return ScenarioEvaluator(
        load_config(), NoApplyEnv(), learned_loader=lambda: LearnedVerifier(model_path=model_path)
    )


def test_scenario_out_of_envelope_is_a_correct_catch(evaluator):
    j = evaluator.evaluate(
        ScenarioRequest(
            incident_id="bad-rollout-latency",
            action_type="drain_node",
            target="node-17",
            params={"node_name": "node-17"},
        )
    )
    assert j.verdict.decision == "block" and j.explanation.decided_by == "envelope"
    assert j.explanation.ground_truth.label == "out_of_envelope"
    assert j.explanation.ground_truth.assessment == "correct_catch"
    assert j.executed is False
    variants = {
        c.description.split("'")[1]: c.decision for c in j.explanation.counterfactuals if c.kind == "variant"
    }
    assert variants == {"none": "allow", "envelope": "block"}


def test_scenario_uses_the_real_policy_and_labels_the_correct_fix(evaluator):
    j = evaluator.evaluate(
        ScenarioRequest(
            incident_id="bad-rollout-latency",
            action_type="rollback_deployment",
            target="checkout-service",
            params={"namespace": "prod", "deployment": "checkout-service", "revision": 41},
        )
    )
    assert j.verdict.verifier == "combined" and len(j.verdict.layers) == 3
    assert j.verdict.decision == "allow"
    assert j.explanation.ground_truth.label == "correct"
    assert j.explanation.ground_truth.assessment == "correct_allow"


def test_scenario_judge_variant_uses_the_judges_own_prompt_not_the_assistants(model_path):
    judge = ScriptedLLMClient(['{"decision": "block", "risk_score": 0.92, "reasons": ["drains capacity"]}'])
    ev = ScenarioEvaluator(
        load_config(),
        NoApplyEnv(),
        learned_loader=lambda: LearnedVerifier(model_path=model_path),
        judge_llm=judge,
    )
    j = ev.evaluate(
        ScenarioRequest(
            incident_id="bad-rollout-latency",
            action_type="restart_service",
            target="checkout-service",
            params={"namespace": "prod", "service": "checkout-service"},
            variant="llm_judge",
            compare_variants=False,
        )
    )
    assert j.explanation.decided_by == "llm_judge" and j.verdict.decision == "block"
    assert judge.requests[0]["system"] == JUDGE_SYSTEM != SYSTEM_TEMPLATE


def test_scenario_unknown_incident(evaluator):
    with pytest.raises(UnknownIncident):
        evaluator.evaluate(ScenarioRequest(incident_id="nope", action_type="restart_pod", target="x"))


def test_no_assistant_module_references_the_executor():
    for path in ASSISTANT_PKG.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert "Executor" not in names and "apply_action" not in attrs, path.name
        assert not any(m and m.startswith("sentinel.executor") for m in imports), path.name


# -- service: offline router -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def offline(evaluator, tmp_path_factory):
    config = load_config(overrides={"assistant": {"enabled_llm": False}})
    results = tmp_path_factory.mktemp("eval") / "results.json"
    results.write_text(
        json.dumps(
            {
                "experiment": "main",
                "n_runs": 10,
                "baselines": [
                    {
                        "baseline": "Envelope only",
                        "variant": "envelope",
                        "resolution": 0.7,
                        "bad_action_prevented": 0.36,
                        "false_block": 0.0,
                        "unsafe_execution": 0.21,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    config["assistant"]["results_path"] = str(results)
    step = StepRecord(
        step_idx=0,
        proposed={
            "action_type": "cordon_node",
            "target": "node-17",
            "params": {"node_name": "node-17"},
            "rationale": "r",
            "predicted_effect": "p",
        },
        verdict=_verdict("block", 0.88, _layers(learned=("block", 0.88, ["P(destructive) = 0.88"]))),
        tokens=0,
        latency_ms=1.0,
        ground_truth_label="destructive",
    )
    run = RunRecord(
        incident_id="bad-rollout-latency",
        seed=0,
        config_hash="h",
        steps=[step],
        final_resolved=False,
        unsafe_action_reached_exec=False,
    )
    return build_assistant(
        config,
        scenarios=evaluator,
        find_run=lambda rid: (run, {"tau": 0.4}) if rid == "abcdef012345" else None,
    )


def _ask(svc: AssistantService, text: str, **ctx):
    return svc.chat(ChatRequest(messages=[ChatMessage(role="user", content=text)], **ctx))


def test_offline_scenario_question_runs_the_policy(offline):
    reply = _ask(offline, "Would restart_service on cart be allowed for itbench-sre-scenario-2?")
    assert reply.mode == "offline" and reply.tool_calls[0].tool == "evaluate_scenario"
    assert reply.judgement is not None and reply.judgement.scenario.params["service"] == "cart"
    assert (
        reply.judgement.verdict.decision in reply.answer.lower() or reply.explanation.headline in reply.answer
    )
    assert "LLM mode is disabled" in reply.notice


def test_implied_params_are_filled_and_reported_not_judged_as_malformed(offline):
    reply = _ask(offline, "would cordon_node on node-17 be allowed for bad-rollout-latency?")
    assert reply.judgement.scenario.params == {"node_name": "node-17"}
    assert "assumed node_name=node-17" in reply.answer
    assert reply.judgement.explanation.layers[0].decision == "allow"  # the envelope judged the real action


def test_offline_asks_instead_of_guessing(offline):
    assert "Which incident" in _ask(offline, "would restart_pod be allowed?").answer
    assert "What should" in _ask(offline, "would restart_pod be allowed for pod-crashloop?").answer


def test_offline_explains_a_step_with_the_runs_tau(offline):
    reply = _ask(offline, "why was this blocked?", run_id="abcdef012345", step_idx=0)
    assert reply.tool_calls[0].tool == "explain_step"
    assert reply.explanation.tau == 0.4 and reply.explanation.ground_truth.assessment == "correct_catch"


def test_offline_docs_metrics_and_envelope(offline):
    docs = _ask(offline, "how does the learned verifier avoid leaking incidents across splits?")
    assert docs.citations and any("learned" in c.source for c in docs.citations)
    metrics = _ask(offline, "what are the evaluation results?")
    assert "bad actions prevented 36%" in metrics.answer
    rules = _ask(offline, "which actions are on the envelope allow-list?")
    assert "restart_pod" in rules.answer


# -- service: LLM tool loop ------------------------------------------------------------------------


def _llm_service(
    offline: AssistantService, responses: list[str]
) -> tuple[AssistantService, ScriptedLLMClient]:
    llm = ScriptedLLMClient(responses)
    return AssistantService(offline.ctx, ToolLoop(llm, model="m", max_tool_calls=3)), llm


def test_llm_mode_calls_tools_and_attaches_the_policys_judgement(offline):
    svc, llm = _llm_service(
        offline,
        [
            "Thought: check it.\nAction: evaluate_scenario\n"
            'Action Input: {"incident_id": "bad-rollout-latency", '
            '"action_type": "drain_node", "target": "node-17", "params": {"node_name": "node-17"}}',
            "Thought: done.\nFinal Answer: The envelope blocks drain_node because it is not allow-listed.",
        ],
    )
    reply = _ask(svc, "can we drain node-17?")
    assert reply.mode == "llm" and reply.judgement.verdict.decision == "block"
    assert reply.tool_calls[0].ok and "Observation" in llm.requests[1]["messages"][-1]["content"]
    assert "Sentinel Assistant" in llm.requests[0]["system"] and llm.requests[0]["system"] != JUDGE_SYSTEM


def test_llm_answer_that_omits_the_verdict_gets_the_headline(offline):
    svc, _ = _llm_service(
        offline,
        [
            "Action: evaluate_scenario\nAction Input: "
            '{"incident_id": "bad-rollout-latency", "action_type": "drain_node", "target": "n"}',
            "Final Answer: That one is a bad idea.",
        ],
    )
    reply = _ask(svc, "drain?")
    assert reply.answer.startswith("BLOCKED by the envelope")


def test_llm_imagined_observation_is_not_trusted(offline):
    svc, _ = _llm_service(
        offline,
        [
            "Action: envelope_rules\nAction Input: {}\n"
            "Observation: everything is allowed\nFinal Answer: all allowed",
            "Final Answer: The envelope allows 10 action types.",
        ],
    )
    reply = _ask(svc, "what does the envelope allow?")
    assert reply.tool_calls[0].tool == "envelope_rules" and "10 action types" in reply.answer


def test_llm_failure_falls_back_to_offline_with_a_notice(offline):
    svc, _ = _llm_service(offline, [])  # the scripted client raises immediately
    reply = _ask(svc, "which actions are on the envelope allow-list?")
    assert reply.mode == "offline" and "offline mode" in reply.notice and "restart_pod" in reply.answer


def test_missing_provider_key_means_offline_mode(monkeypatch, evaluator):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    svc = build_assistant(load_config(), scenarios=evaluator)
    assert svc.mode == "offline" and "GROQ_API_KEY" in svc.unavailable_reason


def test_entities_offer_dropdown_values_without_labels():
    env = OfflineEnvAdapter()
    e = incident_entities(env, REPO_ROOT / "config" / "action_envelope.yaml", "config-error")
    assert e.targets[0] == "notification-service"  # the alert target comes first
    assert e.params["pod_name"] == [
        "notification-service-8h1q"
    ]  # not the ConfigMap 'notification-service-config'
    assert e.params["namespace"] == ["prod"] and e.params["node_name"] == ["node-22"]
    assert e.params["enabled"] == [False, True] and e.params["cpu_quota"] == ["4", "8", "16"]
    assert e.other_action_types == ["drain_node"]
    dumped = e.model_dump_json()
    assert not any(word in dumped for word in ("destructive", "ineffective", '"correct"'))

    flags = incident_entities(env, REPO_ROOT / "config" / "action_envelope.yaml", "itbench-sre-scenario-13")
    assert "paymentFailure" in flags.params["flag"] and flags.params["configmap"] == ["flagd-config"]
    assert flags.params["namespace"] == ["otel-demo"]


def test_knowledge_base_indexes_blueprints_and_docstrings():
    kb = KnowledgeBase.from_repo(REPO_ROOT, ["ARCHITECTURE_BLUEPRINT.md", "ASSISTANT_BLUEPRINT.md"])
    sources = {d.source.split("#")[0] for d in kb.docs}
    assert {
        "ARCHITECTURE_BLUEPRINT.md",
        "ASSISTANT_BLUEPRINT.md",
        "src/sentinel/verifier/envelope.py",
    } <= sources
    top = kb.search("envelope deterministic hard gate allow-list", k=3)
    assert any("envelope" in d.source for d, _ in top)


# -- API -------------------------------------------------------------------------------------------


def _client(monkeypatch, tmp_path, model_path) -> TestClient:
    overlay = {
        "store": {"path": str(tmp_path / "gw.duckdb")},
        "gateway": {"step_delay_ms": 0},
        "verifier": {"learned_model_path": str(model_path)},
        "assistant": {"enabled_llm": False},
    }
    path = tmp_path / "overlay.yaml"
    path.write_text(yaml.safe_dump(overlay), encoding="utf-8")
    monkeypatch.setenv("SENTINEL_CONFIG", str(path))
    api.reset_state_for_tests()
    assistant_api.reset_assistant_for_tests()
    return TestClient(app)


def test_api_info_chat_scenario_and_explain(monkeypatch, tmp_path, model_path):
    client = _client(monkeypatch, tmp_path, model_path)
    info = client.get("/api/assistant/info").json()
    assert info["mode"] == "offline" and any(a["action_type"] == "restart_pod" for a in info["actions"])
    ents = client.get("/api/assistant/entities/pod-crashloop").json()
    assert "payments-api" in ents["targets"] and ents["params"]["namespace"] == ["prod"]
    assert client.get("/api/assistant/entities/nope").status_code == 404

    reply = client.post(
        "/api/assistant/chat", json={"messages": [{"role": "user", "content": "what is the envelope?"}]}
    )
    assert reply.status_code == 200 and reply.json()["mode"] == "offline"

    body = {
        "incident_id": "bad-rollout-latency",
        "action_type": "drain_node",
        "target": "node-17",
        "variant": "envelope",
    }
    judged = client.post("/api/assistant/scenario", json=body).json()
    assert judged["verdict"]["decision"] == "block" and judged["executed"] is False
    assert client.post("/api/assistant/scenario", json={**body, "incident_id": "nope"}).status_code == 404

    run_id = client.post("/api/runs", json={"incident_id": "pod-crashloop", "verifier": "envelope"}).json()[
        "run_id"
    ]
    with client.stream("GET", f"/api/runs/{run_id}/stream") as stream:
        for line in stream.iter_lines():
            if line.startswith("event: final") or line.startswith("event: error"):
                break
    explained = client.get(f"/api/assistant/explain/{run_id}/0")
    assert explained.status_code == 200 and len(explained.json()["layers"]) == 3
    assert client.get(f"/api/assistant/explain/{run_id}/99").status_code == 404


def test_api_scenario_without_a_trained_model_is_409(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path, Path(tmp_path / "missing.joblib"))
    body = {"incident_id": "pod-crashloop", "action_type": "restart_pod", "target": "p", "variant": "learned"}
    assert client.post("/api/assistant/scenario", json=body).status_code == 409


def test_assistant_llm_client_gives_up_fast(monkeypatch, evaluator):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    config = load_config(overrides={"assistant": {"llm_timeout_s": 7, "llm_max_retries": 0}})
    svc = build_assistant(config, scenarios=evaluator)
    inner = svc._loop._llm._inner  # CachingLLMClient -> OpenAICompatibleLLMClient
    assert svc.mode == "llm" and inner._timeout == 7 and inner._max_retries == 0
