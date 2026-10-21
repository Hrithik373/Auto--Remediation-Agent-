# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Builds the configured agent (agent.kind = react | simulated) with its own LLM client.
# Called by orchestrator/factory.py when a run is wired up.
"""Builds the configured DiagnosisAgent (config `agent.kind`: react | simulated)."""

from __future__ import annotations

from sentinel.agent.base import DiagnosisAgent
from sentinel.context.builder import ALL_SIGNALS
from sentinel.env.base import EnvAdapter
from sentinel.gateway.clients import LLMClient, build_llm_client


def build_agent(
    config: dict,
    env: EnvAdapter,
    *,
    seed: int = 0,
    llm: LLMClient | None = None,
    signals: frozenset[str] = ALL_SIGNALS,
) -> DiagnosisAgent:
    agent_cfg = config.get("agent", {})
    kind = agent_cfg.get("kind", "simulated")
    if kind == "react":
        from sentinel.agent.react import ReActDiagnosisAgent

        return ReActDiagnosisAgent(
            llm or build_llm_client(config, provider=config["models"].get("diagnosis_agent_provider")),
            model=config["models"]["diagnosis_agent"],
            max_tool_calls=agent_cfg.get("max_tool_calls", 8),
            max_tokens=config["models"].get("max_tokens_per_call", 4096),
            signals=signals,
        )
    if kind == "simulated":
        from sentinel.agent.simulated import SimulatedDiagnosisAgent

        candidate_actions = getattr(env, "candidate_actions", None)
        if candidate_actions is None:
            raise ValueError(
                "agent.kind=simulated needs an env exposing candidate_actions() (OfflineEnvAdapter)"
            )
        sim = agent_cfg.get("simulated", {})
        augmented = bool(sim.get("include_augmented", True))
        return SimulatedDiagnosisAgent(
            lambda incident_id: candidate_actions(incident_id, augmented=augmented),
            seed=seed,
            label_mix=sim.get("label_mix"),
            feedback_correct_boost=sim.get("feedback_correct_boost", 1.5),
        )
    raise ValueError(f"unknown agent.kind {kind!r}; expected 'react' or 'simulated'")
