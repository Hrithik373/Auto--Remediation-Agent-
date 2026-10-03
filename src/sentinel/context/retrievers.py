"""Log/metric/trace selectors used by context/builder.py (blueprint §3).

All selection is deterministic (no randomness, stable sort keys) so the same incident always yields
the same agent prompt -- a precondition for the LLM disk cache to hit on eval reruns.
"""

from __future__ import annotations

import re

from sentinel.schemas.incident import Telemetry

CHARS_PER_TOKEN = 4  # coarse estimate; budgets are targets, not hard API limits
_ERRORISH = re.compile(
    r"\b(5\d\d|fatal|error|exception|fail(ed|ure)?|timeout|timed out|refused|unavailable|oom\w*|"
    r"backoff|crash\w*|evict\w*|pressure|exhaust\w*|deadline|panic|warn\w*)\b",
    re.IGNORECASE,
)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def select_logs(telemetry: Telemetry, budget_tokens: int) -> list[str]:
    """Error-ish lines first (then the rest), cut to budget, returned in original (time) order."""
    indexed = list(enumerate(telemetry.logs))
    ranked = sorted(indexed, key=lambda pair: (0 if _ERRORISH.search(pair[1]) else 1, pair[0]))
    kept, used = [], 0
    for idx, line in ranked:
        cost = estimate_tokens(line)
        if used + cost > budget_tokens:
            continue
        kept.append((idx, line))
        used += cost
    return [line for _, line in sorted(kept)]


def _change_score(series: list[float]) -> float:
    """Relative spread of a series -- flat series carry little diagnostic signal."""
    if not series:
        return 0.0
    lo, hi = min(series), max(series)
    return (hi - lo) / (abs(lo) + 1.0)


def downsample(series: list[float], max_points: int) -> list[float]:
    if len(series) <= max_points:
        return list(series)
    step = (len(series) - 1) / (max_points - 1)
    return [series[round(i * step)] for i in range(max_points)]


def select_metrics(telemetry: Telemetry, budget_tokens: int, max_points: int = 12) -> dict[str, list[float]]:
    """Most-changing series first, each downsampled, until the budget is spent."""
    ordered = sorted(telemetry.metrics.items(), key=lambda kv: (-_change_score(kv[1]), kv[0]))
    selected: dict[str, list[float]] = {}
    used = 0
    for name, series in ordered:
        points = downsample(series, max_points)
        cost = estimate_tokens(f"{name}: {points}")
        if used + cost > budget_tokens:
            continue
        selected[name] = points
        used += cost
    return selected


def select_traces(telemetry: Telemetry, budget_tokens: int) -> list[dict]:
    """Error spans first, then the rest, until the budget is spent."""
    ordered = sorted(telemetry.traces, key=lambda s: 0 if str(s.get("status", "")).lower() == "error" else 1)
    selected, used = [], 0
    for span in ordered:
        cost = estimate_tokens(str(span))
        if used + cost > budget_tokens:
            continue
        selected.append(span)
        used += cost
    return selected
