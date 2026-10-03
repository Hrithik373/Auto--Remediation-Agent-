"""AIOpsLab (Microsoft) EnvAdapter. Stub — cluster integration is parallel/non-blocking work per
ARCHITECTURE_BLUEPRINT.md §8: "If cluster setup slips, the offline path still gives you a complete,
defensible Review 2 and Final."

Per CLAUDE.md: "Never make a core module import a cluster client at module top-level" — the AIOpsLab
client library must be imported lazily, inside each method, not here.
"""

from __future__ import annotations

from sentinel.env.base import EnvAdapter
from sentinel.schemas.action import ExecutionResult, ProposedAction
from sentinel.schemas.incident import IncidentContext


class AIOpsLabEnvAdapter(EnvAdapter):
    """EnvAdapter backed by a live AIOpsLab (kind/minikube) deployment. Not yet implemented."""

    def __init__(self, *, kubeconfig: str | None = None, aiopslab_config: str | None = None) -> None:
        self._kubeconfig = kubeconfig
        self._aiopslab_config = aiopslab_config

    def list_incidents(self) -> list[str]:
        raise NotImplementedError("AIOpsLabEnvAdapter is not implemented yet. Use OfflineEnvAdapter.")

    def get_incident(self, incident_id: str) -> IncidentContext:
        raise NotImplementedError("AIOpsLabEnvAdapter is not implemented yet. Use OfflineEnvAdapter.")

    def apply_action(self, action: ProposedAction, dry_run: bool) -> ExecutionResult:
        raise NotImplementedError("AIOpsLabEnvAdapter is not implemented yet. Use OfflineEnvAdapter.")

    def evaluate(self, incident_id: str) -> bool:
        raise NotImplementedError("AIOpsLabEnvAdapter is not implemented yet. Use OfflineEnvAdapter.")

    def ground_truth_action_safe(self, action: ProposedAction, incident_id: str) -> bool | None:
        raise NotImplementedError("AIOpsLabEnvAdapter is not implemented yet. Use OfflineEnvAdapter.")
