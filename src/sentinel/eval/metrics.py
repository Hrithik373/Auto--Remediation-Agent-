"""Metrics computed from RunRecords — blueprint §7. Phase P4.

resolution rate, bad-action-prevented rate, false-block rate, net safe resolutions, MTTM, cost.
Per CLAUDE.md: "Don't invent metrics; use the ones in eval/metrics.py" -- this module is the single
source of truth other phases (and the report) must cite.
"""

from __future__ import annotations

from sentinel.schemas.run import RunRecord


def resolution_rate(runs: list[RunRecord]) -> float:
    raise NotImplementedError(
        "eval.metrics.resolution_rate is Phase P4 work. See ARCHITECTURE_BLUEPRINT.md §7."
    )


def bad_action_prevented_rate(runs: list[RunRecord]) -> float:
    raise NotImplementedError(
        "eval.metrics.bad_action_prevented_rate is Phase P4 work. See ARCHITECTURE_BLUEPRINT.md §7."
    )


def false_block_rate(runs: list[RunRecord]) -> float:
    raise NotImplementedError(
        "eval.metrics.false_block_rate is Phase P4 work. See ARCHITECTURE_BLUEPRINT.md §7."
    )


def net_safe_resolutions(runs: list[RunRecord]) -> float:
    raise NotImplementedError(
        "eval.metrics.net_safe_resolutions is Phase P4 work. See ARCHITECTURE_BLUEPRINT.md §7."
    )


def mean_time_to_mitigation(runs: list[RunRecord]) -> float:
    raise NotImplementedError(
        "eval.metrics.mean_time_to_mitigation is Phase P4 work. See ARCHITECTURE_BLUEPRINT.md §7."
    )


def cost_per_incident(runs: list[RunRecord]) -> float:
    raise NotImplementedError(
        "eval.metrics.cost_per_incident is Phase P4 work. See ARCHITECTURE_BLUEPRINT.md §7."
    )
