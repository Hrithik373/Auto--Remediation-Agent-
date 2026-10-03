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
from sentinel.verifier.llm_judge import JUDGE_SYSTEM, LLMJudgeVerifier, parse_judge_output
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
    verdict = LLMJudgeVerifier(ScriptedLLMClient([bad])).verify(incident, ROLLBACK)
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
