# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# The assistant's LLM tool loop: Thought -> Action (read-only tool) -> Observation ... -> Final Answer.
# In-repo and small on purpose (no agent framework); any failure lets service.py answer offline.
"""Assistant tool loop (ASSISTANT_BLUEPRINT.md §6, LLM mode).

Same text protocol as agent/react.py, but its own prompt, its own client and its own ledger. Tool
results are kept as structured ToolResults so the reply's judgement / explanation / citations come
from the tools, never from parsing the model's prose.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from sentinel.assistant.prompts import system_prompt
from sentinel.assistant.tools import TOOLS, AssistantContext, ToolError, ToolResult, run_tool
from sentinel.gateway.clients import LLMClient, UsageLedger
from sentinel.schemas.assistant import ChatMessage, ToolCall

_ACTION_RE = re.compile(r"Action\s*:\s*([\w-]+)\s*(?:\n|$)(?:.*?Action Input\s*:\s*(\{.*\}))?", re.S | re.I)
_FINAL_RE = re.compile(r"final answer\s*:\s*(.*)", re.S | re.I)


class LoopFailed(RuntimeError):
    pass


@dataclass
class LoopOutcome:
    answer: str
    calls: list[ToolCall] = field(default_factory=list)
    results: list[ToolResult] = field(default_factory=list)


def tool_lines() -> str:
    return "\n".join(f"- {t.name}: {t.description}. args: {t.args}" for t in TOOLS.values())


class ToolLoop:
    def __init__(
        self, llm: LLMClient, *, model: str, max_tool_calls: int = 5, max_tokens: int = 1500
    ) -> None:
        self._llm = llm
        self._model = model
        self._max_tool_calls = max_tool_calls
        self._max_tokens = max_tokens
        self._system = system_prompt(tool_lines())
        self.usage = UsageLedger()  # the assistant's own -- never the agent's or the judge's

    def _call(self, history: list[dict]) -> str:
        response = self._llm.complete(
            system=self._system, messages=history, model=self._model, max_tokens=self._max_tokens
        )
        self.usage.record(response)
        history.append({"role": "assistant", "content": response.text})
        return response.text

    def _act(self, ctx: AssistantContext, text: str, outcome: LoopOutcome) -> str:
        match = _ACTION_RE.search(text)
        if not match:
            return "Observation: reply with either 'Action:' + 'Action Input:' or 'Final Answer:'."
        name = match.group(1)
        try:
            args = json.loads(match.group(2)) if match.group(2) else {}
            if not isinstance(args, dict):
                raise ToolError("Action Input must be a JSON object")
            result = run_tool(ctx, name, args)
        except (json.JSONDecodeError, ToolError) as exc:
            outcome.calls.append(ToolCall(tool=name, args={}, ok=False, summary=str(exc)))
            return f"Observation: tool call failed: {exc}"
        outcome.calls.append(ToolCall(tool=name, args=args, ok=True, summary=result.summary))
        outcome.results.append(result)
        return f"Observation:\n{result.text}"

    def run(self, ctx: AssistantContext, messages: list[ChatMessage], context_note: str = "") -> LoopOutcome:
        history = [{"role": m.role, "content": m.content} for m in messages]
        if context_note:
            history[-1] = {"role": "user", "content": f"{history[-1]['content']}\n\n({context_note})"}
        outcome = LoopOutcome(answer="")
        for _ in range(self._max_tool_calls + 1):
            text = self._call(history)
            final = _FINAL_RE.search(text)
            action = _ACTION_RE.search(text)
            # An Action before the Final Answer means the model imagined the tool's output: run it instead.
            if final and final.group(1).strip() and not (action and action.start() < final.start()):
                outcome.answer = final.group(1).strip()
                return outcome
            history.append({"role": "user", "content": self._act(ctx, text, outcome)})
        history.append(
            {"role": "user", "content": "Observation: tool budget used up. Give your Final Answer now."}
        )
        final = _FINAL_RE.search(self._call(history))
        if not final or not final.group(1).strip():
            raise LoopFailed(f"no Final Answer within {self._max_tool_calls} tool calls")
        outcome.answer = final.group(1).strip()
        return outcome
