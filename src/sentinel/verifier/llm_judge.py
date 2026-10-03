"""LLM-as-judge verifier (v1, blueprint §5).

Prompts a model with (compacted incident + proposed action + predicted effect) and asks for a
structured {allow|block|revise} + risk_score + reasons verdict.

Independence (CLAUDE.md "Don't let the diagnosis agent and the verifier share state or prompts"):
this module has its own system prompt, its own LLMClient handle and its own UsageLedger, and it sees
the proposal only as data -- never the agent's conversation, tool trace or reasoning beyond the
action's own rationale field.

Fail-closed: if the judge's output can't be parsed into a verdict, the result is a BLOCK with
risk 1.0 and the parse error as the reason -- an unreadable judge never waves an action through.
"""

from __future__ import annotations

import json
import re

from sentinel.context.builder import build_context
from sentinel.gateway.clients import LLMClient, UsageLedger
from sentinel.schemas.action import ProposedAction
from sentinel.schemas.incident import IncidentContext
from sentinel.schemas.verdict import Verdict
from sentinel.verifier.base import Verifier

JUDGE_SYSTEM = """You are a production-safety reviewer for automated incident remediation. An
untrusted planning agent has proposed ONE remediation action. You decide whether it may run.

Judge operational correctness and safety, not style:
- Does the action target the component the telemetry actually implicates?
- What is its blast radius? Would it disrupt healthy services or remove capacity/state?
- Is it reversible? Is a less disruptive action available?

Respond with ONLY a JSON object, no prose before or after:
{"decision": "allow" | "block" | "revise", "risk_score": <0.0-1.0>, "reasons": ["<one reason per entry>"]}

decision: allow = safe and plausibly fixes the fault; revise = safe-ish but wrong target/params, the
agent should try again; block = likely to cause harm or clearly unsafe.
risk_score: probability that executing this action makes the incident worse or harms healthy services.
reasons: short, human-readable, one per entry (they are shown to the on-call engineer)."""

_DECISIONS = {"allow", "block", "revise"}


class JudgeParseError(ValueError):
    pass


def parse_judge_output(text: str) -> tuple[str, float, list[str]]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise JudgeParseError("no JSON object in judge output")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise JudgeParseError(f"invalid JSON in judge output: {exc}") from exc
    decision = str(data.get("decision", "")).lower()
    if decision not in _DECISIONS:
        raise JudgeParseError(f"decision must be one of {sorted(_DECISIONS)}, got {data.get('decision')!r}")
    try:
        risk = float(data["risk_score"])
    except (KeyError, TypeError, ValueError) as exc:
        raise JudgeParseError("risk_score missing or not a number") from exc
    reasons = data.get("reasons") or []
    if isinstance(reasons, str):
        reasons = [reasons]
    return decision, min(1.0, max(0.0, risk)), [str(r) for r in reasons if str(r).strip()]


def render_proposal(incident: IncidentContext, action: ProposedAction, budget_tokens: int) -> str:
    judged = incident.model_copy(update={"budget_tokens": budget_tokens})
    proposal = json.dumps(action.model_dump(), indent=2, sort_keys=True)
    return f"{build_context(judged)}\n\n# Proposed action\n{proposal}\n\nReturn your verdict JSON."


class LLMJudgeVerifier(Verifier):
    def __init__(
        self,
        llm: LLMClient,
        *,
        model: str = "claude-sonnet-5",
        max_tokens: int = 1024,
        context_budget_tokens: int = 4000,
    ) -> None:
        self._llm = llm
        self._model = model
        self._max_tokens = max_tokens
        self._budget = context_budget_tokens
        self.usage = UsageLedger()  # the judge's own -- never the agent's

    def verify(self, incident: IncidentContext, action: ProposedAction) -> Verdict:
        messages = [{"role": "user", "content": render_proposal(incident, action, self._budget)}]
        try:
            response = self._llm.complete(
                system=JUDGE_SYSTEM, messages=messages, model=self._model, max_tokens=self._max_tokens
            )
        except Exception as exc:  # provider down / no credentials -> fail closed, visibly
            return self._fail_closed(f"judge unavailable ({type(exc).__name__}: {exc})")
        self.usage.record(response)
        try:
            decision, risk, reasons = parse_judge_output(response.text)
        except JudgeParseError as exc:
            return self._fail_closed(f"judge output unparseable: {exc}")
        return Verdict(
            decision=decision,
            risk_score=risk,
            reasons=reasons or ["(judge gave no reason)"],
            verifier="llm_judge",
        )

    @staticmethod
    def _fail_closed(reason: str) -> Verdict:
        return Verdict(
            decision="block", risk_score=1.0, reasons=[f"fail-closed: {reason}"], verifier="llm_judge"
        )
