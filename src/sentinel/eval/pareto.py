"""Sweeps the verifier threshold tau and plots bad-action-prevented vs. false-block (and vs.
resolution rate) -- the headline risk-autonomy Pareto figure. Phase P4, blueprint §7.
"""

from __future__ import annotations

from sentinel.schemas.run import RunRecord


def sweep_threshold(runs_by_tau: dict[float, list[RunRecord]]) -> list[dict]:
    raise NotImplementedError(
        "eval.pareto.sweep_threshold is Phase P4 work. See ARCHITECTURE_BLUEPRINT.md §7."
    )
