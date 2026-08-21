"""Prometheus metrics — Phase P5. Not implemented yet; see PROGRESS.md.

Intended counters/histograms: verdicts by decision, actions executed, unsafe actions blocked,
per-step latency, per-incident cost. Wired to the docker-compose.yml `prometheus`/`grafana` services.
"""

from __future__ import annotations


def init_metrics() -> None:
    raise NotImplementedError(
        "observability.metrics.init_metrics is Phase P5 work. See ARCHITECTURE_BLUEPRINT.md §8."
    )
