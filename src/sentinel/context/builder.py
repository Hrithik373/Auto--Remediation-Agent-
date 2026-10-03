"""Telemetry -> LLM context: compaction, token budgeting, redaction (blueprint §3).

Hard rule: `IncidentContext.fault_family` is NEVER rendered -- it is eval-only ground truth, and
leaking it would make diagnosis trivial (schemas/incident.py). The rendered context contains only
what an on-call engineer could observe: alerts, topology, metrics, traces, logs.
"""

from __future__ import annotations

import json
import re

from sentinel.context.retrievers import estimate_tokens, select_logs, select_metrics, select_traces
from sentinel.schemas.incident import IncidentContext

ALL_SIGNALS = frozenset({"alerts", "topology", "metrics", "traces", "logs"})

# Budget split across the variable-size sections (alerts/topology are small and always kept whole).
_SHARE = {"metrics": 0.2, "traces": 0.15, "logs": 0.65}

_REDACTIONS = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "<email>"),
    (re.compile(r"(?i)\b(bearer|token|password|passwd|secret|api[_-]?key)\b([=: ]+)\S+"), r"\1\2<redacted>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<ip>"),
]


def redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def _section(title: str, body: str) -> str:
    return f"## {title}\n{body.strip() or '(none)'}\n"


def _render_topology(topology: dict) -> str:
    lines = []
    if topology.get("services"):
        lines.append("entities: " + ", ".join(map(str, topology["services"])))
    for edge in topology.get("edges", []):
        lines.append(f"{edge[0]} -> {edge[1]}")
    if topology.get("edge_semantics"):
        lines.append(f"(edges: {topology['edge_semantics']})")
    return "\n".join(lines)


def build_context(incident: IncidentContext, signals: frozenset[str] | set[str] = ALL_SIGNALS) -> str:
    """Render the incident for the diagnosis agent within `incident.budget_tokens`.

    `signals` selects which telemetry sources are visible -- the telemetry-signal ablation in
    blueprint §7 (e.g. {"logs"} for logs-only).
    """
    unknown = set(signals) - ALL_SIGNALS
    if unknown:
        raise ValueError(f"unknown signals {sorted(unknown)}; expected a subset of {sorted(ALL_SIGNALS)}")
    t = incident.telemetry
    # No incident_id in the header: the hand-built P0 ids name their fault ("pod-crashloop",
    # "memory-leak-oom", ...), which would hand the agent the diagnosis.
    parts = ["# Incident under investigation\n"]
    if "alerts" in signals:
        parts.append(_section("Alerts", "\n".join(json.dumps(a, sort_keys=True) for a in t.alerts)))
    if "topology" in signals:
        parts.append(_section("Topology", _render_topology(t.topology)))

    fixed = estimate_tokens("".join(parts))
    variable = max(0, incident.budget_tokens - fixed)
    active = [s for s in ("metrics", "traces", "logs") if s in signals]
    share_total = sum(_SHARE[s] for s in active) or 1.0
    budget = {s: int(variable * _SHARE[s] / share_total) for s in active}

    if "metrics" in signals:
        metrics = select_metrics(t, budget["metrics"])
        parts.append(
            _section("Metrics (oldest -> newest)", "\n".join(f"{k}: {v}" for k, v in metrics.items()))
        )
    if "traces" in signals:
        traces = select_traces(t, budget["traces"])
        parts.append(_section("Traces", "\n".join(json.dumps(s, sort_keys=True) for s in traces)))
    if "logs" in signals:
        parts.append(_section("Logs", "\n".join(select_logs(t, budget["logs"]))))
    return redact("\n".join(parts))
