# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Abstract EnvAdapter: list/get incidents, apply an action, report the oracle outcome.
# Every environment implements it, so the rest of the system is cluster-agnostic.
"""EnvAdapter ABC — the only thing that touches the benchmark (blueprint §5).

Every concrete adapter (offline, AIOpsLab, ITBench) implements this exact interface so the rest of
the system — agent, verifier, executor, orchestrator, eval harness — is cluster-agnostic. Per
CLAUDE.md: "Never make a core module import a cluster client at module top-level" — cluster-backed
adapters must import their client libraries lazily, inside methods.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sentinel.schemas.action import ExecutionResult, ProposedAction
from sentinel.schemas.incident import IncidentContext


class EnvAdapter(ABC):
    """Cluster-agnostic environment interface. See offline_adapter.py for the reference implementation."""

    @abstractmethod
    def list_incidents(self) -> list[str]:
        """Return all incident IDs this adapter can serve."""
        raise NotImplementedError

    @abstractmethod
    def get_incident(self, incident_id: str) -> IncidentContext:
        """Fetch telemetry/context for one incident."""
        raise NotImplementedError

    @abstractmethod
    def apply_action(self, action: ProposedAction, dry_run: bool) -> ExecutionResult:
        """Execute (or simulate, if dry_run) a verified action against the environment."""
        raise NotImplementedError

    @abstractmethod
    def evaluate(self, incident_id: str) -> bool:
        """Oracle check: is the incident resolved right now?"""
        raise NotImplementedError

    def reset(self, incident_id: str) -> None:  # noqa: B027 -- optional hook, default no-op
        """Return the incident to its initial (unresolved) state before a run. Adapters backed by a
        real cluster re-inject the fault here; the default is a no-op."""

    @abstractmethod
    def ground_truth_action_safe(self, action: ProposedAction, incident_id: str) -> bool | None:
        """Label source for the verifier's training/eval data (labeling/oracle_labeler.py, Phase P3).

        Returns True/False if a ground-truth safety label is derivable for this action, else None.
        """
        raise NotImplementedError
