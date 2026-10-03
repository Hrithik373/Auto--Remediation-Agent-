"""Telemetry tools the ReAct diagnosis agent calls over the current incident (blueprint §3).

get_logs / get_metrics / get_traces / get_topology. Each reads the current IncidentContext.telemetry
and nothing else; none of them touch EnvAdapter.apply_action -- the agent only ever produces a
ProposedAction (propose.py), it never executes. The registry below is what the agent's prompt
advertises, and `run_tool` is the only dispatch path, so a tool for an ablated signal (blueprint §7
telemetry-signal ablation) is genuinely unavailable rather than merely unmentioned.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

from sentinel.context.builder import ALL_SIGNALS, redact
from sentinel.schemas.incident import IncidentContext

MAX_LOG_LINES = 40
MAX_OBSERVATION_CHARS = 6000


def get_logs(incident: IncidentContext, query: str | None = None) -> list[str]:
    """Log lines matching `query` (case-insensitive regex, falling back to substring), capped."""
    logs = incident.telemetry.logs
    if query:
        try:
            pattern = re.compile(query, re.IGNORECASE)
            logs = [line for line in logs if pattern.search(line)]
        except re.error:
            logs = [line for line in logs if query.lower() in line.lower()]
    return logs[:MAX_LOG_LINES]


def get_metrics(incident: IncidentContext, names: list[str] | None = None) -> dict[str, list[float]]:
    metrics = incident.telemetry.metrics
    if names:
        metrics = {k: v for k, v in metrics.items() if k in set(names)}
    return dict(metrics)


def get_traces(incident: IncidentContext) -> list[dict]:
    return list(incident.telemetry.traces)


def get_topology(incident: IncidentContext) -> dict:
    return dict(incident.telemetry.topology)


@dataclass(frozen=True)
class Tool:
    name: str
    signal: str
    description: str
    args: str
    fn: Callable[..., object]


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        Tool(
            "get_logs",
            "logs",
            "Search the incident's log lines.",
            '{"query": "<regex or text, optional>"}',
            lambda inc, query=None: get_logs(inc, query),
        ),
        Tool(
            "get_metrics",
            "metrics",
            "Metric time series (oldest -> newest).",
            '{"names": ["<metric>", ...]}',
            lambda inc, names=None: get_metrics(inc, names),
        ),
        Tool(
            "get_traces",
            "traces",
            "Trace spans recorded during the incident.",
            "{}",
            lambda inc: get_traces(inc),
        ),
        Tool(
            "get_topology",
            "topology",
            "Service/entity dependency graph.",
            "{}",
            lambda inc: get_topology(inc),
        ),
    )
}


class ToolError(ValueError):
    """Bad tool name/arguments. Surfaced to the agent as an observation, never raised past it."""


def available_tools(signals: frozenset[str] | set[str] = ALL_SIGNALS) -> list[Tool]:
    return [t for t in TOOLS.values() if t.signal in signals]


def run_tool(
    incident: IncidentContext, name: str, args: dict, signals: frozenset[str] | set[str] = ALL_SIGNALS
) -> str:
    """Execute one tool call and render its result as a (redacted, size-capped) observation string."""
    tool = TOOLS.get(name)
    if tool is None or tool.signal not in signals:
        raise ToolError(
            f"unknown or unavailable tool '{name}'; available: {[t.name for t in available_tools(signals)]}"
        )
    try:
        result = tool.fn(incident, **args)
    except TypeError as exc:
        raise ToolError(f"bad arguments for {name}: {exc}; expected {tool.args}") from exc
    text = redact(json.dumps(result, sort_keys=True, default=str))
    if len(text) > MAX_OBSERVATION_CHARS:
        text = text[:MAX_OBSERVATION_CHARS] + " ...(truncated)"
    return text
