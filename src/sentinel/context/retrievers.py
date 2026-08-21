"""Log/metric/trace/topology selectors used by context/builder.py — Phase P1."""

from __future__ import annotations

from sentinel.schemas.incident import Telemetry


def select_logs(telemetry: Telemetry, budget_tokens: int) -> list[str]:
    raise NotImplementedError(
        "context.retrievers.select_logs is Phase P1 work. See ARCHITECTURE_BLUEPRINT.md §3."
    )


def select_metrics(telemetry: Telemetry, budget_tokens: int) -> dict[str, list[float]]:
    raise NotImplementedError(
        "context.retrievers.select_metrics is Phase P1 work. See ARCHITECTURE_BLUEPRINT.md §3."
    )
