"""Wires an Orchestrator from config: env, agent, verifier variant, executor.

The agent and the judge each get their OWN LLM client handle and ledger (CLAUDE.md independence).
The learned verifier (Phase P3) is loaded from verifier.learned_model_path when a variant needs it.
"""

from __future__ import annotations

from sentinel.agent.factory import build_agent
from sentinel.config import config_hash, resolve_path
from sentinel.context.builder import ALL_SIGNALS
from sentinel.env.base import EnvAdapter
from sentinel.executor.executor import Executor
from sentinel.gateway.clients import LLMClient, build_llm_client
from sentinel.orchestrator.loop import Orchestrator
from sentinel.verifier.base import Verifier
from sentinel.verifier.envelope import EnvelopeVerifier
from sentinel.verifier.policy import build_policy


def build_judge(config: dict, llm: LLMClient | None = None) -> Verifier:
    from sentinel.verifier.llm_judge import LLMJudgeVerifier

    return LLMJudgeVerifier(llm or build_llm_client(config), model=config["models"]["llm_judge"])


def build_learned(config: dict) -> Verifier:
    from sentinel.verifier.learned import LearnedVerifier

    return LearnedVerifier(model_path=resolve_path(config["verifier"]["learned_model_path"]))


def build_verifier(
    config: dict,
    variant: str,
    tau: float,
    *,
    judge_llm: LLMClient | None = None,
    learned: Verifier | None = None,
) -> Verifier:
    needs_judge = variant in ("llm_judge", "combined")
    needs_learned = variant in ("learned", "combined")
    envelope = (
        None if variant == "none" else EnvelopeVerifier(resolve_path(config["verifier"]["envelope_config"]))
    )
    return build_policy(
        variant,
        threshold=tau,
        envelope=envelope,
        judge=build_judge(config, judge_llm) if needs_judge else None,
        learned=(learned or build_learned(config)) if needs_learned else None,
    )


def build_orchestrator(
    config: dict,
    env: EnvAdapter,
    *,
    variant: str | None = None,
    tau: float | None = None,
    seed: int = 0,
    agent_llm: LLMClient | None = None,
    judge_llm: LLMClient | None = None,
    learned: Verifier | None = None,
    signals: frozenset[str] = ALL_SIGNALS,
) -> Orchestrator:
    variant = variant or config["verifier"]["active"]
    tau = config["verifier"]["threshold"] if tau is None else tau
    resolved = {
        **config,
        "verifier": {**config["verifier"], "active": variant, "threshold": tau},
        "run": {"seed": seed, "signals": sorted(signals)},
    }
    return Orchestrator(
        env,
        build_agent(config, env, seed=seed, llm=agent_llm, signals=signals),
        build_verifier(config, variant, tau, judge_llm=judge_llm, learned=learned),
        Executor(env, auto_execute=bool(config["execution"]["auto_execute"])),
        max_steps=config["budgets"]["max_steps"],
        config_hash=config_hash(resolved),
        on_block=config["orchestrator"].get("on_block", "escalate"),
    )
