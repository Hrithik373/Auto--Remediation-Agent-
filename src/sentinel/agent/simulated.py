"""SimulatedDiagnosisAgent -- a seeded, LLM-free proposal generator.

WHAT THIS IS (and isn't): a controlled stimulus for evaluating the VERIFIER, not a diagnosis method.
It samples each proposal from the incident's oracle candidates (fixture `oracle.labeled_actions`)
according to a configured label mix -- e.g. 45% correct, 20% destructive -- standing in for an
imperfect LLM planner so the whole pipeline and the eval harness run offline, deterministically, and
at zero cost. Reported results must say which agent produced them (RunRecords carry config_hash; the
agent kind is in the config).

Leak guard: the agent reads oracle labels to *choose*, but the ProposedAction it emits carries only
label-independent text -- the same rationale/predicted_effect template for every candidate -- so no
verifier can recover the label from the proposal's wording. Verifiers never see the oracle.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from sentinel.agent.base import AgentExhausted, DiagnosisAgent
from sentinel.schemas.action import ProposedAction
from sentinel.schemas.incident import IncidentContext

LABELS = ("correct", "ineffective", "destructive", "out_of_envelope")
CandidateSource = Callable[[str], list[dict]]  # incident_id -> oracle labeled_actions


class SimulatedDiagnosisAgent(DiagnosisAgent):
    def __init__(
        self,
        candidates: CandidateSource,
        *,
        seed: int = 0,
        label_mix: dict[str, float] | None = None,
        feedback_correct_boost: float = 1.5,
    ) -> None:
        super().__init__()
        self._candidates = candidates
        self._seed = seed
        self._mix = dict(
            label_mix or {"correct": 0.45, "ineffective": 0.25, "destructive": 0.2, "out_of_envelope": 0.1}
        )
        self._boost = feedback_correct_boost
        self._state: dict[str, dict] = {}

    def propose(self, incident: IncidentContext) -> ProposedAction:
        # String seeds hash deterministically (random.seed version 2), so (seed, incident) -> same run.
        self._state[incident.incident_id] = {
            "rng": random.Random(f"{self._seed}:{incident.incident_id}"),
            "weights": dict(self._mix),
            "tried": set(),
        }
        return self._next(incident)

    def incorporate_feedback(self, incident: IncidentContext, reasons: list[str]) -> ProposedAction:
        state = self._state.get(incident.incident_id)
        if state is None:
            return self.propose(incident)
        state["weights"]["correct"] = state["weights"].get("correct", 0.0) * self._boost
        return self._next(incident)

    def _next(self, incident: IncidentContext) -> ProposedAction:
        state = self._state[incident.incident_id]
        untried = [c for c in self._candidates(incident.incident_id) if _key(c) not in state["tried"]]
        by_label = {label: [c for c in untried if c.get("label") == label] for label in LABELS}
        labels = [label for label in LABELS if by_label[label] and state["weights"].get(label, 0) > 0]
        if not labels:
            raise AgentExhausted(f"no untried candidate actions left for {incident.incident_id}")
        label = state["rng"].choices(labels, weights=[state["weights"][x] for x in labels])[0]
        choice = state["rng"].choice(sorted(by_label[label], key=_key))
        state["tried"].add(_key(choice))
        return _to_action(choice)


def _key(candidate: dict) -> str:
    return f"{candidate['action_type']}|{candidate['target']}|{sorted(candidate.get('params', {}).items())}"


def _to_action(candidate: dict) -> ProposedAction:
    action_type, target = candidate["action_type"], candidate["target"]
    return ProposedAction(
        action_type=action_type,
        target=target,
        params=dict(candidate.get("params", {})),
        rationale=f"Telemetry points at '{target}'; proposing {action_type} to mitigate the symptoms.",
        predicted_effect=f"{action_type} on '{target}' should clear the active alerts.",
    )
