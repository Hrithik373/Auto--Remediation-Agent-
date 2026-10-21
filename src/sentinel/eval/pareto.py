# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Sweeps the risk threshold tau and builds the risk-vs-autonomy Pareto front.
# Feeds the headline figure and the console's Pareto chart.
"""The risk-autonomy Pareto (blueprint §7): sweep tau, plot bad-action-prevented vs false-block (and vs
resolution). The headline figure; tau is the trade-off knob the console's ParetoChart drags.
"""

from __future__ import annotations

from sentinel.eval.metrics import (
    bad_action_prevented_rate,
    false_block_rate,
    net_safe_resolutions,
    resolution_rate,
    unsafe_execution_rate,
)
from sentinel.schemas.run import RunRecord


def sweep_threshold(runs_by_tau: dict[float, list[RunRecord]]) -> list[dict]:
    """One point per tau (ascending): the metrics that trade off against each other."""
    return [
        {
            "tau": tau,
            "bad_action_prevented": bad_action_prevented_rate(runs),
            "false_block": false_block_rate(runs),
            "resolution": resolution_rate(runs),
            "net_safe_resolutions": net_safe_resolutions(runs),
            "unsafe_execution": unsafe_execution_rate(runs),
            "n_runs": len(runs),
        }
        for tau, runs in sorted(runs_by_tau.items())
    ]


def pareto_front(points: list[dict], x: str = "false_block", y: str = "bad_action_prevented") -> list[dict]:
    """Points not dominated by another (lower-or-equal x AND higher-or-equal y, one strictly)."""
    valid = [p for p in points if p.get(x) is not None and p.get(y) is not None]
    front = []
    for p in valid:
        dominated = any(q[x] <= p[x] and q[y] >= p[y] and (q[x] < p[x] or q[y] > p[y]) for q in valid)
        if not dominated:
            front.append(p)
    return sorted(front, key=lambda p: p[x])
