# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Judges "what if the agent proposed X on incident Y?" by running the REAL verifier policy (verify only).
# Adds the oracle ground-truth label and the decision under other variants; never executes anything.
"""ScenarioEvaluator (ASSISTANT_BLUEPRINT.md §4, §5).

The judgement is whatever verifier.policy returns -- this module only builds the ProposedAction,
calls .verify(), and explains the result. It holds no reference to an executor and never calls
EnvAdapter.apply_action: the environment is used read-only, for the incident and its oracle labels.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from sentinel.assistant.explain import assess, explain_verdict
from sentinel.config import resolve_path
from sentinel.env.base import EnvAdapter
from sentinel.env.offline_adapter import OfflineEnvAdapter
from sentinel.gateway.clients import LLMClient
from sentinel.labeling.oracle_labeler import derive_label_with_provenance
from sentinel.orchestrator.factory import build_learned, build_verifier
from sentinel.schemas.action import ProposedAction
from sentinel.schemas.assistant import Counterfactual, ScenarioJudgement, ScenarioRequest
from sentinel.schemas.verdict import Verdict
from sentinel.verifier.base import Verifier

# Variants that need no LLM: cheap enough to compare on every scenario.
OFFLINE_VARIANTS = ("none", "envelope", "learned")


class UnknownIncident(ValueError):
    pass


def scenario_action(req: ScenarioRequest) -> ProposedAction:
    """The proposal, worded with the same label-free template the simulated agent uses, so the learned
    verifier sees the scenario exactly as it would see an agent proposal."""
    return ProposedAction(
        action_type=req.action_type,
        target=req.target,
        params=req.params,
        rationale=req.rationale
        or f"Telemetry points at '{req.target}'; proposing {req.action_type} to mitigate the symptoms.",
        predicted_effect=f"{req.action_type} on '{req.target}' should clear the active alerts.",
    )


class ScenarioEvaluator:
    def __init__(
        self,
        config: dict,
        env: EnvAdapter | None = None,
        *,
        learned_loader: Callable[[], Verifier] | None = None,
        judge_llm: LLMClient | None = None,
    ) -> None:
        self._config = config
        fixtures = resolve_path(config.get("env", {}).get("fixtures_dir", "fixtures/incidents"))
        self._env = env or OfflineEnvAdapter(fixtures)
        self._learned_loader = learned_loader or (lambda: build_learned(config))
        self._learned: Verifier | None = None
        self._judge_llm = judge_llm
        self._lock = threading.Lock()  # the offline adapter tracks a "current" incident

    def _learned_verifier(self) -> Verifier:
        if self._learned is None:
            self._learned = self._learned_loader()  # FileNotFoundError if `make train` never ran
        return self._learned

    def _verify(self, variant: str, tau: float, incident, action: ProposedAction) -> Verdict:
        learned = self._learned_verifier() if variant in ("learned", "combined") else None
        policy = build_verifier(self._config, variant, tau, judge_llm=self._judge_llm, learned=learned)
        return policy.verify(incident, action)

    def _compare(self, req: ScenarioRequest, incident, action: ProposedAction) -> list[Counterfactual]:
        out = []
        for variant in OFFLINE_VARIANTS:
            if variant == req.variant:
                continue
            try:
                verdict = self._verify(variant, req.tau, incident, action)
            except FileNotFoundError:
                continue  # no trained learned model: nothing to compare against
            out.append(
                Counterfactual(
                    kind="variant",
                    description=(
                        f"With the '{variant}' variant: {verdict.decision} "
                        f"(risk {verdict.risk_score:.2f})."
                    ),
                    decision=verdict.decision,
                )
            )
        return out

    def evaluate(self, req: ScenarioRequest) -> ScenarioJudgement:
        with self._lock:
            if req.incident_id not in self._env.list_incidents():
                raise UnknownIncident(f"unknown incident {req.incident_id!r}")
            incident = self._env.get_incident(req.incident_id)
            action = scenario_action(req)
            verdict = self._verify(req.variant, req.tau, incident, action)
            label, provenance = derive_label_with_provenance(self._env, action, req.incident_id)
            explanation = explain_verdict(verdict, req.tau, assess(label, verdict.decision, provenance))
            if req.compare_variants:
                explanation.counterfactuals.extend(self._compare(req, incident, action))
        return ScenarioJudgement(scenario=req, action=action, verdict=verdict, explanation=explanation)
