"""Phase P2: LLM judge (with a scripted LLM) and the CombinedPolicy layering. The learned verifier is
covered in test_learned.py (Phase P3). EnvelopeVerifier is covered in test_envelope.py.
"""

from __future__ import annotations

import json

import pytest

from sentinel.env.offline_adapter import OfflineEnvAdapter
from sentinel.gateway.clients import ScriptedLLMClient
from sentinel.schemas.action import ProposedAction
from sentinel.schemas.verdict import Verdict
from sentinel.verifier.base import Verifier
from sentinel.verifier.llm_judge import JUDGE_SYSTEM, JudgeParseError, LLMJudgeVerifier, parse_judge_output
from sentinel.verifier.policy import CombinedPolicy, build_policy

CORDON = ProposedAction(
    action_type="cordon_node",
    target="node-17",
    params={"node_name": "node-17"},
    rationale="node looks busy",
    predicted_effect="latency drops",
)
ROLLBACK = ProposedAction(
    action_type="rollback_deployment",
    target="checkout-service",
    params={"namespace": "prod", "deployment": "checkout-service", "revision": 41},
    rationale="rev 42 added a blocking call",
    predicted_effect="latency recovers",
)
SCALE_ZERO = ProposedAction(
    action_type="scale_deployment",
    target="auth-service",
    params={"namespace": "prod", "deployment": "auth-service", "replicas": 0},
    rationale="r",
    predicted_effect="e",
)


@pytest.fixture(scope="module")
def incident():
    return OfflineEnvAdapter().get_incident("bad-rollout-latency")


class FixedVerifier(Verifier):
    def __init__(self, decision: str, risk: float, name: str = "learned") -> None:
        self.calls = 0
        self._verdict = Verdict(
            decision=decision, risk_score=risk, reasons=[f"{name} says {decision}"], verifier=name
        )

    def verify(self, incident, action):
        self.calls += 1
        return self._verdict


# -- LLM judge ------------------------------------------------------------------------------------


def test_judge_blocks_destructive_action(incident):
    llm = ScriptedLLMClient(
        [
            '{"decision": "block", "risk_score": 0.87, '
            '"reasons": ["cordons a healthy node; unrelated to the bad revision"]}'
        ]
    )
    judge = LLMJudgeVerifier(llm)
    verdict = judge.verify(incident, CORDON)
    assert verdict.decision == "block" and verdict.risk_score == 0.87 and verdict.verifier == "llm_judge"
    assert judge.usage.calls == 1


def test_judge_prompt_is_independent_of_the_agent(incident):
    llm = ScriptedLLMClient(['{"decision": "allow", "risk_score": 0.1, "reasons": ["ok"]}'])
    LLMJudgeVerifier(llm).verify(incident, ROLLBACK)
    request = llm.requests[0]
    assert request["system"] == JUDGE_SYSTEM and "diagnosis agent" not in request["system"]
    sent = json.dumps(request)
    assert "bad-rollout-latency" not in sent and incident.fault_family not in sent
    assert "rollback_deployment" in sent  # the proposal is passed as data


@pytest.mark.parametrize(
    "bad", ["looks fine to me", '{"decision": "maybe", "risk_score": 0.2}', '{"decision": "allow"}']
)
def test_judge_fails_closed_on_unparseable_output(incident, bad):
    llm = ScriptedLLMClient([bad, bad])  # the corrective re-ask gets the same garbage back
    verdict = LLMJudgeVerifier(llm).verify(incident, ROLLBACK)
    assert len(llm.requests) == 2
    assert verdict.decision == "block" and verdict.risk_score == 1.0
    assert verdict.reasons[0].startswith("fail-closed")


def test_judge_fails_closed_when_llm_unavailable(incident):
    verdict = LLMJudgeVerifier(ScriptedLLMClient([])).verify(incident, ROLLBACK)  # raises inside
    assert verdict.decision == "block" and "unavailable" in verdict.reasons[0]


def test_parse_judge_output_clamps_risk():
    assert parse_judge_output('{"decision": "ALLOW", "risk_score": 7, "reasons": "fine"}') == (
        "allow",
        1.0,
        ["fine"],
    )


def test_parse_judge_output_ignores_trailing_prose():
    text = 'Verdict:\n{"decision": "allow", "risk_score": 0.1, "reasons": ["ok"]}\n\n{"note": "extra"} done.'
    assert parse_judge_output(text) == ("allow", 0.1, ["ok"])


def test_judge_context_budget_comes_from_config():
    from sentinel.config import load_config
    from sentinel.orchestrator.factory import build_judge

    config = load_config(overrides={"budgets": {"judge_context_tokens": 1234}})
    judge = build_judge(config, ScriptedLLMClient([]))
    assert judge._budget == 1234


# -- CombinedPolicy -------------------------------------------------------------------------------


def test_policy_always_reports_all_three_layers(incident):
    verdict = build_policy("envelope", threshold=0.5).verify(incident, ROLLBACK)
    assert [layer.verifier for layer in verdict.layers] == ["envelope", "llm_judge", "learned"]
    assert [layer.decision for layer in verdict.layers] == ["allow", "skipped", "skipped"]
    assert verdict.verifier == "combined"


def test_envelope_block_short_circuits_secondary(incident):
    learned = FixedVerifier("allow", 0.0)
    verdict = build_policy("learned", threshold=0.5, learned=learned).verify(incident, SCALE_ZERO)
    assert verdict.decision == "block" and learned.calls == 0
    assert verdict.layers[2].decision == "skipped" and "already blocked" in verdict.layers[2].reasons[0]


def test_secondary_catches_what_the_envelope_passes(incident):
    # The thesis in one assertion: cordon_node is structurally valid (envelope allows) but risky.
    verdict = build_policy("learned", threshold=0.5, learned=FixedVerifier("block", 0.91)).verify(
        incident, CORDON
    )
    assert verdict.layers[0].decision == "allow"
    assert verdict.decision == "block" and verdict.risk_score == 0.91


def test_threshold_is_the_knob(incident):
    learned = FixedVerifier("allow", 0.4)
    assert (
        build_policy("learned", threshold=0.5, learned=learned).verify(incident, ROLLBACK).decision == "allow"
    )
    assert (
        build_policy("learned", threshold=0.3, learned=learned).verify(incident, ROLLBACK).decision == "block"
    )


def test_revise_only_when_no_layer_over_tau_wants_block(incident):
    judge = FixedVerifier("revise", 0.6, name="llm_judge")
    assert (
        build_policy("llm_judge", threshold=0.5, judge=judge).verify(incident, ROLLBACK).decision == "revise"
    )
    both = build_policy("combined", threshold=0.5, judge=judge, learned=FixedVerifier("block", 0.7))
    assert both.verify(incident, ROLLBACK).decision == "block"


def test_ungated_baseline_allows_everything(incident):
    verdict = build_policy("none", threshold=0.5).verify(incident, CORDON)
    assert verdict.decision == "allow" and all(layer.decision == "skipped" for layer in verdict.layers)


def test_envelope_only_still_responds_to_tau(incident):
    # rollback_deployment has blast_radius=medium (risk 0.35): allowed at tau 0.5, blocked at 0.3.
    assert build_policy("envelope", threshold=0.5).verify(incident, ROLLBACK).decision == "allow"
    assert build_policy("envelope", threshold=0.3).verify(incident, ROLLBACK).decision == "block"


def test_policy_validation():
    with pytest.raises(ValueError):
        build_policy("learned", threshold=0.5)  # learned verifier not provided
    with pytest.raises(ValueError):
        CombinedPolicy(None, None, threshold=1.5)


# -- provider request limits (e.g. Groq free tier: 7000 input tokens/minute) ----------------------

OK_VERDICT = '{"decision": "allow", "risk_score": 0.1, "reasons": ["ok"]}'


class TooLargeOnceClient(ScriptedLLMClient):
    """Rejects the first request as too large (HTTP 413), like Groq does, then answers."""

    def __init__(self, failures: int = 1):
        super().__init__([OK_VERDICT])
        self.failures = failures
        self.sizes: list[int] = []

    def complete(self, *, system, messages, model, max_tokens):
        self.sizes.append(len(messages[0]["content"]))
        if self.failures:
            self.failures -= 1
            raise RuntimeError(
                "HTTP 413 from https://api.groq.com: Request too large for model on input tokens"
            )
        return super().complete(system=system, messages=messages, model=model, max_tokens=max_tokens)


def test_judge_shrinks_its_prompt_to_the_providers_input_cap():
    big = OfflineEnvAdapter().get_incident("itbench-sre-scenario-13")
    llm = ScriptedLLMClient([OK_VERDICT])
    verdict = LLMJudgeVerifier(llm, context_budget_tokens=8000, max_input_tokens=3000).verify(big, ROLLBACK)
    sent = len(JUDGE_SYSTEM) + len(llm.requests[0]["messages"][0]["content"])
    assert sent / 2.5 <= 3000
    assert verdict.decision == "allow" and "trimmed" in verdict.reasons[-1]


def test_judge_without_a_cap_sends_the_full_budget(incident):
    llm = ScriptedLLMClient([OK_VERDICT])
    verdict = LLMJudgeVerifier(llm, context_budget_tokens=4000).verify(incident, ROLLBACK)
    assert verdict.reasons == ["ok"]  # nothing trimmed, no note


def test_judge_retries_with_half_the_context_on_413():
    big = OfflineEnvAdapter().get_incident("itbench-sre-scenario-13")
    llm = TooLargeOnceClient(failures=1)
    verdict = LLMJudgeVerifier(llm, context_budget_tokens=8000).verify(big, ROLLBACK)
    assert verdict.decision == "allow" and len(llm.sizes) == 2 and llm.sizes[1] < llm.sizes[0]
    assert "trimmed" in verdict.reasons[-1]


def test_judge_still_fails_closed_when_nothing_fits_or_on_other_errors(incident):
    verdict = LLMJudgeVerifier(TooLargeOnceClient(failures=99), context_budget_tokens=8000).verify(
        incident, ROLLBACK
    )
    assert verdict.decision == "block" and verdict.risk_score == 1.0 and "413" in verdict.reasons[0]
    other = LLMJudgeVerifier(ScriptedLLMClient([])).verify(incident, ROLLBACK)  # RuntimeError, not 413
    assert other.decision == "block" and "unavailable" in other.reasons[0]


# -- malformed judge JSON (seen live on Groq/qwen: the final "}" was missing) ------------------------

GROQ_REPLY_MISSING_BRACE = (
    '{"decision": "block", "risk_score": 0.9, "reasons": ["The telemetry indicates a configuration failure '
    'in \'notification-service\'.", "This action is ineffective and likely to miss the root cause."]'
)


def test_reply_cut_off_before_its_closing_brace_is_closed_not_rewritten():
    assert parse_judge_output(GROQ_REPLY_MISSING_BRACE) == (
        "block",
        0.9,
        [
            "The telemetry indicates a configuration failure in 'notification-service'.",
            "This action is ineffective and likely to miss the root cause.",
        ],
    )
    cut_mid_reason = '{"decision": "allow", "risk_score": 0.2, "reasons": ["restarts are rev'
    assert parse_judge_output(cut_mid_reason) == ("allow", 0.2, ["restarts are rev"])


@pytest.mark.parametrize(
    "bad",
    [
        '{"decision": "allow", "risk_score": 0.1]',  # mismatched bracket: not an unfinished object
        '{"decision": "allow" "risk_score": 0.1}',  # error in the middle, not at the end
        '{"decision": "allow", "reasons": ["x"',  # closable, but risk_score is still missing
    ],
)
def test_other_malformed_json_is_still_an_error(bad):
    with pytest.raises(JudgeParseError):
        parse_judge_output(bad)


def test_judge_reasks_once_and_uses_the_corrected_reply(incident):
    llm = ScriptedLLMClient(['{"decision": "allow" "risk_score": 0.1}', OK_VERDICT])
    judge = LLMJudgeVerifier(llm)
    verdict = judge.verify(incident, ROLLBACK)
    assert verdict.decision == "allow" and verdict.reasons == ["ok"]
    assert "not valid JSON" in llm.requests[1]["messages"][-1]["content"]
    assert judge.usage.calls == 2


def test_live_groq_reply_now_gives_the_judges_real_verdict(incident):
    verdict = LLMJudgeVerifier(ScriptedLLMClient([GROQ_REPLY_MISSING_BRACE])).verify(incident, ROLLBACK)
    assert verdict.decision == "block" and verdict.risk_score == 0.9
    assert not verdict.reasons[0].startswith("fail-closed")


# -- tightened decision rules: facts from the allow-list, decision-matched risk bands --------------


def test_judge_sees_the_allow_lists_facts_not_a_guess(incident):
    llm = ScriptedLLMClient([OK_VERDICT])
    restart = ROLLBACK.model_copy(
        update={"action_type": "restart_service", "params": {"namespace": "prod", "service": "x"}}
    )
    LLMJudgeVerifier(llm).verify(incident, restart)
    sent = llm.requests[0]["messages"][0]["content"]
    assert "# Action facts (from the allow-list)" in sent
    assert "blast_radius: low" in sent and "reversible: True" in sent
    system = llm.requests[0]["system"]
    assert "do not re-estimate blast radius" in system
    assert 'A wrong target alone is "revise", not "block"' in system


def test_a_revise_in_the_revise_band_is_sent_back_not_allowed_or_blocked(incident):
    """The revise band (0.55-0.75) sits above the default tau, so the policy really returns 'revise'."""
    from sentinel.verifier.envelope import EnvelopeVerifier

    judge = LLMJudgeVerifier(
        ScriptedLLMClient(['{"decision": "revise", "risk_score": 0.65, "reasons": ["wrong target"]}'])
    )
    restart = ROLLBACK.model_copy(
        update={"action_type": "restart_service", "params": {"namespace": "prod", "service": "x"}}
    )
    verdict = build_policy("llm_judge", threshold=0.5, envelope=EnvelopeVerifier(), judge=judge).verify(
        incident, restart
    )
    assert verdict.decision == "revise" and "wrong target" in verdict.reasons
