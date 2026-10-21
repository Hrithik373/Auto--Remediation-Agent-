"""ReAct diagnosis agent (blueprint §3, §5). In-repo and readable on purpose -- : "Don't add a
heavy agent framework".

Text protocol (model-agnostic; works with any LLMClient). Each assistant turn is one of:

    Thought: ...                       Thought: ...
    Action: <tool name>          or    Final Answer: {<ProposedAction JSON>}
    Action Input: {<json args>}

Tool results come back as `Observation: ...` user turns. Malformed turns are answered with an
observation explaining the problem, never silently repaired. The prompt here belongs to the agent
alone -- the verifier has its own, independent prompt and state ().
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from sentinel.agent.base import AgentExhausted, DiagnosisAgent
from sentinel.agent.propose import ProposalParseError, parse_proposed_action
from sentinel.agent.tools import ToolError, available_tools, run_tool
from sentinel.context.builder import ALL_SIGNALS, build_context
from sentinel.gateway.clients import LLMClient
from sentinel.schemas.action import ProposedAction
from sentinel.schemas.incident import IncidentContext

_DEFAULT_ENVELOPE = Path(__file__).resolve().parents[3] / "config" / "action_envelope.yaml"
_ACTION_RE = re.compile(r"Action\s*:\s*([\w-]+)\s*(?:\n|$)(?:.*?Action Input\s*:\s*(\{.*\}))?", re.S | re.I)

SYSTEM_TEMPLATE = """You are an on-call SRE diagnosis agent. Investigate the incident with the tools,
identify the most likely root cause, and propose exactly ONE remediation action.

Nothing you propose is executed directly: an independent safety verifier reviews it first, and a
human may be paged. Prefer the least disruptive action that addresses the root cause.

Tools:
{tools}

Remediation actions you may propose (action_type: params):
{actions}

Reply with EXACTLY one of these two formats per turn:

Thought: <your reasoning>
Action: <tool name>
Action Input: <JSON object of tool arguments>

or, when ready:

Thought: <your reasoning>
Final Answer: {{"action_type": "...", "target": "...", "params": {{...}},
               "rationale": "...", "predicted_effect": "..."}}
"""


def action_catalog(envelope_path: Path = _DEFAULT_ENVELOPE) -> str:
    """The allow-listed action types, so the agent knows its vocabulary (not the verifier's rules)."""
    with envelope_path.open(encoding="utf-8") as f:
        actions = yaml.safe_load(f)["allowed_actions"]
    lines = []
    for name, spec in actions.items():
        params = ", ".join(
            f"{p}{'' if rule.get('required') else '?'}: {rule.get('type', 'string')}"
            for p, rule in spec.get("params", {}).items()
        )
        lines.append(f"- {name}: {{{params}}}")
    return "\n".join(lines)


class ReActDiagnosisAgent(DiagnosisAgent):
    def __init__(
        self,
        llm: LLMClient,
        *,
        model: str = "qwen/qwen3.8-27b",
        max_tool_calls: int = 8,
        max_tokens: int = 4096,
        signals: frozenset[str] = ALL_SIGNALS,
    ) -> None:
        super().__init__()
        self._llm = llm
        self._model = model
        self._max_tool_calls = max_tool_calls
        self._max_tokens = max_tokens
        self._signals = frozenset(signals)
        tools = "\n".join(
            f"- {t.name}: {t.description} args: {t.args}" for t in available_tools(self._signals)
        )
        self._system = SYSTEM_TEMPLATE.format(tools=tools, actions=action_catalog())
        self._history: dict[str, list[dict]] = {}

    def propose(self, incident: IncidentContext) -> ProposedAction:
        task = (
            f"{build_context(incident, self._signals)}\n\nDiagnose this incident and propose one "
            "remediation action."
        )
        self._history[incident.incident_id] = [{"role": "user", "content": task}]
        return self._loop(incident)

    def incorporate_feedback(self, incident: IncidentContext, reasons: list[str]) -> ProposedAction:
        history = self._history.get(incident.incident_id)
        if history is None:
            return self.propose(incident)
        bullet = "\n".join(f"- {r}" for r in reasons) or "- (no reason given)"
        history.append(
            {
                "role": "user",
                "content": (
                    "Observation: your previous proposal was NOT executed as-is. Feedback:\n"
                    f"{bullet}\nPropose a different or corrected action."
                ),
            }
        )
        return self._loop(incident)

    def _call(self, history: list[dict]) -> str:
        response = self._llm.complete(
            system=self._system, messages=history, model=self._model, max_tokens=self._max_tokens
        )
        self.usage.record(response)
        history.append({"role": "assistant", "content": response.text})
        return response.text

    def _observe(self, incident: IncidentContext, text: str) -> str:
        """Run the tool call in `text`, or explain what was wrong with the turn."""
        match = _ACTION_RE.search(text)
        if not match:
            return "Observation: reply with either 'Action:' + 'Action Input:' or 'Final Answer:'."
        try:
            args = json.loads(match.group(2)) if match.group(2) else {}
            if not isinstance(args, dict):
                raise ToolError("Action Input must be a JSON object")
            return "Observation: " + run_tool(incident, match.group(1), args, self._signals)
        except (json.JSONDecodeError, ToolError) as exc:
            return f"Observation: tool call failed: {exc}"

    def _loop(self, incident: IncidentContext) -> ProposedAction:
        history = self._history[incident.incident_id]
        for _ in range(self._max_tool_calls):
            text = self._call(history)
            if re.search(r"final answer\s*:", text, re.I):
                try:
                    return parse_proposed_action(text)
                except ProposalParseError as exc:
                    history.append(
                        {"role": "user", "content": f"Observation: {exc}. Give a corrected Final Answer."}
                    )
                    continue
            history.append({"role": "user", "content": self._observe(incident, text)})
        history.append(
            {"role": "user", "content": "Observation: tool budget exhausted. Give your Final Answer now."}
        )
        try:
            return parse_proposed_action(self._call(history))
        except ProposalParseError as exc:
            raise AgentExhausted(
                f"no valid proposal within {self._max_tool_calls} tool calls: {exc}"
            ) from exc
