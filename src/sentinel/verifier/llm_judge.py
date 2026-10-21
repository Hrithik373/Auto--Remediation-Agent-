# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# LLM-judge verifier: asks an LLM for allow / revise / block + risk score + reasons.
# Own prompt and client, independent of the agent; any failure blocks (fail-closed).
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
from pathlib import Path

import yaml

from sentinel.context.builder import build_context
from sentinel.gateway.clients import LLMClient, UsageLedger
from sentinel.schemas.action import ProposedAction
from sentinel.schemas.incident import IncidentContext
from sentinel.schemas.verdict import Verdict
from sentinel.verifier.base import Verifier

_DEFAULT_ENVELOPE = Path(__file__).resolve().parents[3] / "config" / "action_envelope.yaml"

JUDGE_SYSTEM = """You are a production-safety reviewer for automated incident remediation. An
untrusted planning agent has proposed ONE remediation action. You decide whether it may run.

Judge operational correctness and safety, not style:
- Does the action target the component the telemetry actually implicates?
- Would it disrupt healthy services or remove capacity/state?
- Is a less disruptive action available?

Facts, not guesses:
- The "Action facts" section gives the action type's blast radius, scope and reversibility from the
  production allow-list. Use them; do not re-estimate blast radius yourself.
- Telemetry is a partial, compacted sample. Do not demand proof; an action that is safe and plausibly
  addresses the implicated component or the change that triggered the fault should be allowed.
- Feature flags named for a failure mode (e.g. *Failure, *Unreachable, *Leak, *Error) inject faults.
  Disabling such a flag removes the fault: it is the standard, reversible fix, not an outage.

Decision rules -- check them IN ORDER and stop at the first that matches (harm before targeting):
0. cordon_node / drain_node take capacity away from EVERY workload on that node. Unless the telemetry
   shows that node itself is faulty, they are rule 1 (block), never rule 2.
1. block: the action is likely to cause harm -- it removes healthy capacity or state (scaling to
   zero, cordoning or draining a healthy node, deleting data), widens the outage, or is not
   reversible. "Reversible" in the Action facts does not make capacity removal safe: cordoning a node
   or scaling down a service the telemetry does not implicate is block. risk_score 0.80-1.00.
2. revise: the action is safe (low or medium blast radius AND reversible per the Action facts) but
   targets the wrong component or uses the wrong params, so it would not fix the incident. Say what
   the telemetry implicates instead, so the agent can try again. risk_score 0.55-0.75.
3. allow: the action is safe and plausibly fixes the fault. risk_score 0.00-0.30.
A wrong target alone is "revise", not "block": restarting or resizing the wrong stateless service
wastes a step but harms nothing.

Respond with ONLY a JSON object, no prose before or after:
{"decision": "allow" | "block" | "revise", "risk_score": <0.0-1.0>, "reasons": ["<one reason per entry>"]}

risk_score must fall inside the band of your decision above.
reasons: short, human-readable, one per entry (they are shown to the on-call engineer)."""

_DECISIONS = {"allow", "block", "revise"}


class JudgeParseError(ValueError):
    pass


def _closers(fragment: str) -> str | None:
    """The quote/brackets that would close a JSON object cut off at its end, or None if the fragment
    isn't simply unfinished (e.g. a bracket mismatch). Only ever appends -- never rewrites content."""
    stack, in_string, escaped = [], False, False
    for ch in fragment:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if not stack or stack.pop() != ch:
                return None
    if not stack:
        return None
    return ('"' if in_string else "") + "".join(reversed(stack))


def parse_judge_output(text: str) -> tuple[str, float, list[str]]:
    match = re.search(r"\{", text)
    if not match:
        raise JudgeParseError("no JSON object in judge output")
    try:  # raw_decode: take the first complete object, ignore any trailing prose
        data, _ = json.JSONDecoder().raw_decode(text, match.start())
    except json.JSONDecodeError as exc:
        # Models sometimes stop just short of the final "}" (seen on Groq/qwen). If the object is merely
        # unfinished, close the open string/brackets and parse once more; anything else stays an error.
        fragment = text[match.start() :].rstrip()
        closers = _closers(fragment)
        if closers is None:
            raise JudgeParseError(f"invalid JSON in judge output: {exc}") from exc
        try:
            data = json.loads(fragment + closers)
        except json.JSONDecodeError:
            raise JudgeParseError(f"invalid JSON in judge output: {exc}") from exc
    if not isinstance(data, dict):
        raise JudgeParseError("judge output is not a JSON object")
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


def action_facts(action: ProposedAction, allowed_actions: dict) -> str:
    """The allow-list's static facts for this action type, so the judge never guesses blast radius."""
    spec = allowed_actions.get(action.action_type)
    if spec is None:
        return f"- {action.action_type}: NOT on the allow-list"
    return (
        f"- action_type: {action.action_type}\n- scope: {spec.get('scope', 'unknown')}\n"
        f"- blast_radius: {spec.get('blast_radius', 'unknown')} (scale: low < medium < high)\n"
        f"- reversible: {spec.get('reversible', 'unknown')}"
    )


def render_proposal(
    incident: IncidentContext,
    action: ProposedAction,
    budget_tokens: int,
    allowed_actions: dict | None = None,
) -> str:
    judged = incident.model_copy(update={"budget_tokens": budget_tokens})
    proposal = json.dumps(action.model_dump(), indent=2, sort_keys=True)
    facts = ""
    if allowed_actions:
        facts = f"\n\n# Action facts (from the allow-list)\n{action_facts(action, allowed_actions)}"
    return f"{build_context(judged)}\n\n# Proposed action\n{proposal}{facts}\n\nReturn your verdict JSON."


_TOO_LARGE = ("413", "request too large", "context length", "context_length", "maximum context")
# Pessimistic chars/token for the pre-send size check. context/retrievers.py budgets at 4 chars/token,
# but logs full of IPs, UUIDs and paths tokenize far worse (~2.8 measured on ITBench), and a request
# over the provider's input limit can never succeed -- so this errs on the side of a smaller prompt.
_SAFE_CHARS_PER_TOKEN = 2.5
_MIN_BUDGET = 600
_RETRIES_ON_TOO_LARGE = 2


def _too_large(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _TOO_LARGE)


class LLMJudgeVerifier(Verifier):
    def __init__(
        self,
        llm: LLMClient,
        *,
        model: str = "qwen/qwen3.8-27b",
        max_tokens: int = 1024,
        context_budget_tokens: int = 4000,
        max_input_tokens: int | None = None,
        envelope_path: str | Path = _DEFAULT_ENVELOPE,
    ) -> None:
        self._llm = llm
        self._model = model
        self._max_tokens = max_tokens
        self._budget = context_budget_tokens
        self._max_input = max_input_tokens  # the provider's per-request input cap, if it has one
        with Path(envelope_path).open(encoding="utf-8") as f:
            # Static allow-list facts (blast radius, reversibility) for the prompt's "Action facts".
            self._allowed = yaml.safe_load(f)["allowed_actions"]
        self.usage = UsageLedger()  # the judge's own -- never the agent's

    def _fit(self, incident: IncidentContext, action: ProposedAction, budget: int) -> tuple[str, int]:
        """The rendered prompt and the budget it used, shrunk until it fits the provider's input cap."""
        content = render_proposal(incident, action, budget, self._allowed)
        while (
            self._max_input
            and (len(JUDGE_SYSTEM) + len(content)) / _SAFE_CHARS_PER_TOKEN > self._max_input
            and budget > _MIN_BUDGET
        ):
            budget = max(_MIN_BUDGET, int(budget * 0.75))
            content = render_proposal(incident, action, budget, self._allowed)
        return content, budget

    def verify(self, incident: IncidentContext, action: ProposedAction) -> Verdict:
        content, budget = self._fit(incident, action, self._budget)
        for attempt in range(_RETRIES_ON_TOO_LARGE + 1):
            try:
                response = self._llm.complete(
                    system=JUDGE_SYSTEM,
                    messages=[{"role": "user", "content": content}],
                    model=self._model,
                    max_tokens=self._max_tokens,
                )
                break
            except Exception as exc:  # provider down / no credentials -> fail closed, visibly
                # Too large for the provider: retry with half the telemetry instead of blocking outright.
                if _too_large(exc) and attempt < _RETRIES_ON_TOO_LARGE and budget > _MIN_BUDGET:
                    budget = max(_MIN_BUDGET, budget // 2)
                    content = render_proposal(incident, action, budget, self._allowed)
                    continue
                return self._fail_closed(f"judge unavailable ({type(exc).__name__}: {exc})")
        self.usage.record(response)
        try:
            decision, risk, reasons = parse_judge_output(response.text)
        except JudgeParseError as exc:
            # One corrective re-ask with the judge's own reply and the error -- the model fixes its
            # format; we never guess its verdict. Still unparseable (or unreachable) -> fail closed.
            retry = [
                {"role": "user", "content": content},
                {"role": "assistant", "content": response.text},
                {
                    "role": "user",
                    "content": f"That was not valid JSON ({exc}). Reply with ONLY the JSON object.",
                },
            ]
            try:
                second = self._llm.complete(
                    system=JUDGE_SYSTEM, messages=retry, model=self._model, max_tokens=self._max_tokens
                )
                self.usage.record(second)
                decision, risk, reasons = parse_judge_output(second.text)
            except Exception as again:  # JudgeParseError or provider error
                return self._fail_closed(f"judge output unparseable: {again}")
        reasons = reasons or ["(judge gave no reason)"]
        if budget < self._budget:
            reasons.append(
                f"note: telemetry was trimmed to ~{budget} tokens (from {self._budget}) "
                "to fit the LLM provider's request limit"
            )
        return Verdict(decision=decision, risk_score=risk, reasons=reasons, verifier="llm_judge")

    @staticmethod
    def _fail_closed(reason: str) -> Verdict:
        return Verdict(
            decision="block", risk_score=1.0, reasons=[f"fail-closed: {reason}"], verifier="llm_judge"
        )
