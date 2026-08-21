"""Telemetry tools the ReAct diagnosis agent calls over the current incident — Phase P1.

get_logs / get_metrics / get_traces / get_topology, per ARCHITECTURE_BLUEPRINT.md §3. Each tool reads
from the current IncidentContext.telemetry; none of them touch EnvAdapter.apply_action directly — the
agent only ever produces a ProposedAction (propose.py), it never executes.
"""

from __future__ import annotations

from sentinel.schemas.incident import IncidentContext


def get_logs(incident: IncidentContext, query: str | None = None) -> list[str]:
    raise NotImplementedError("agent.tools.get_logs is Phase P1 work. See ARCHITECTURE_BLUEPRINT.md §3.")


def get_metrics(incident: IncidentContext, names: list[str] | None = None) -> dict[str, list[float]]:
    raise NotImplementedError("agent.tools.get_metrics is Phase P1 work. See ARCHITECTURE_BLUEPRINT.md §3.")


def get_traces(incident: IncidentContext) -> list[dict]:
    raise NotImplementedError("agent.tools.get_traces is Phase P1 work. See ARCHITECTURE_BLUEPRINT.md §3.")


def get_topology(incident: IncidentContext) -> dict:
    raise NotImplementedError("agent.tools.get_topology is Phase P1 work. See ARCHITECTURE_BLUEPRINT.md §3.")
