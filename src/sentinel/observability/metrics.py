# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Defines the Prometheus counters/histograms and records each live step and run outcome.
# Exposed at the gateway's /metrics endpoint.
"""Prometheus metrics for the live loop (blueprint §2, §8 P5), scraped from the gateway's /metrics by
docker-compose.yml's `prometheus` service and charted by the provisioned Grafana dashboard.

Recorded from the console's live runs (gateway/runs.py) -- the eval harness's numbers live in DuckDB,
not here; this is operational telemetry ("what is the verifier doing right now"), not results.
Uses its own CollectorRegistry so tests and reloads never hit duplicate-registration errors.
"""

from __future__ import annotations

from dataclasses import dataclass

from prometheus_client import CollectorRegistry, Counter, Histogram

from sentinel.schemas.run import RunRecord, StepRecord


@dataclass
class SentinelMetrics:
    registry: CollectorRegistry
    verdicts: Counter
    layer_verdicts: Counter
    executions: Counter
    destructive: Counter
    runs: Counter
    step_latency: Histogram
    run_cost: Counter
    run_tokens: Counter


_METRICS: SentinelMetrics | None = None


def init_metrics(registry: CollectorRegistry | None = None) -> SentinelMetrics:
    """Create (once) and return the metric set. Pass a registry to get a fresh, isolated set."""
    global _METRICS
    if _METRICS is not None and registry is None:
        return _METRICS
    reg = registry or CollectorRegistry()
    m = SentinelMetrics(
        registry=reg,
        verdicts=Counter("sentinel_verdicts", "Final verdicts", ["decision", "variant"], registry=reg),
        layer_verdicts=Counter(
            "sentinel_layer_verdicts", "Per-layer verdicts", ["layer", "decision"], registry=reg
        ),
        executions=Counter("sentinel_executions", "Actions handed to the executor", ["mode"], registry=reg),
        destructive=Counter(
            "sentinel_destructive_proposals",
            "Destructive-labeled proposals by outcome",
            ["outcome"],
            registry=reg,
        ),
        runs=Counter("sentinel_runs", "Finished runs by outcome", ["outcome", "variant"], registry=reg),
        step_latency=Histogram(
            "sentinel_step_latency_seconds",
            "Propose+verify+act latency per step",
            buckets=(0.005, 0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10, 30),
            registry=reg,
        ),
        run_cost=Counter("sentinel_llm_cost_usd", "LLM spend (agent + verifier)", registry=reg),
        run_tokens=Counter("sentinel_llm_tokens", "LLM tokens (agent + verifier)", registry=reg),
    )
    if registry is None:
        _METRICS = m
    return m


def record_step(m: SentinelMetrics, step: StepRecord, variant: str) -> None:
    m.verdicts.labels(step.verdict.decision, variant).inc()
    for layer in step.verdict.layers:
        m.layer_verdicts.labels(layer.verifier, layer.decision).inc()
    if step.result is not None:
        m.executions.labels("dry_run" if step.result.dry_run else "apply").inc()
    if step.ground_truth_label == "destructive":
        m.destructive.labels("blocked" if step.verdict.decision != "allow" else "executed").inc()
    m.step_latency.observe(step.latency_ms / 1000)


def run_outcome(run: RunRecord) -> str:
    if run.final_resolved:
        return "resolved"
    if not run.steps:
        return "no_proposal"
    return {"block": "escalated", "revise": "gave_up", "allow": "unresolved"}[run.steps[-1].verdict.decision]


def record_run(m: SentinelMetrics, run: RunRecord, variant: str) -> None:
    m.runs.labels(run_outcome(run), variant).inc()
    m.run_cost.inc(run.total_cost_usd)
    m.run_tokens.inc(run.total_tokens)
