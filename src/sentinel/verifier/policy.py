# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Combines the layers: final = envelope passes AND max secondary risk < tau.
# Always reports all three layers, marking inactive ones as skipped.
"""Verifier policy combinator (blueprint §5): final = envelope_pass AND (score < threshold tau).

The layering is the experiment. Every combined Verdict lists ALL three layers in `layers`
(envelope, llm_judge, learned) -- an inactive layer is present with decision "skipped" so the console
can gray it out (FRONTEND_BLUEPRINT.md §6.1) and the eval can attribute each catch to a layer.

Score: the max risk over the active secondary layers (most conservative); with no secondary layer it
is the envelope's blast-radius risk, so the envelope-only baseline still has a tau curve. Over tau,
the final decision is "revise" only if a layer over tau asked for revise and none asked for block;
otherwise "block". tau is what Phase P4 sweeps to draw the risk-autonomy Pareto curve.
"""

from __future__ import annotations

from sentinel.schemas.action import ProposedAction
from sentinel.schemas.incident import IncidentContext
from sentinel.schemas.verdict import LayerVerdict, Verdict
from sentinel.verifier.base import Verifier
from sentinel.verifier.envelope import EnvelopeVerifier

LAYERS = ("envelope", "llm_judge", "learned")
VARIANTS = ("none", "envelope", "llm_judge", "learned", "combined")


class CombinedPolicy(Verifier):
    """envelope AND (max secondary risk < threshold). `secondaries` maps layer name -> verifier."""

    def __init__(
        self, envelope: EnvelopeVerifier | None, secondaries: dict[str, Verifier] | None, threshold: float
    ) -> None:
        unknown = set(secondaries or {}) - {"llm_judge", "learned"}
        if unknown:
            raise ValueError(f"unknown secondary layers {sorted(unknown)}")
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"threshold tau must be in [0, 1], got {threshold}")
        self._envelope = envelope
        self._secondaries = dict(secondaries or {})
        self.threshold = threshold

    def usage_totals(self) -> tuple[int, float]:
        """(tokens, cost_usd) spent by this policy's LLM-backed layers so far."""
        ledgers = [getattr(v, "usage", None) for v in self._secondaries.values()]
        ledgers = [ledger for ledger in ledgers if ledger is not None]
        return sum(lg.total_tokens for lg in ledgers), sum(lg.cost_usd for lg in ledgers)

    def verify(self, incident: IncidentContext, action: ProposedAction) -> Verdict:
        layers: dict[str, LayerVerdict] = {
            name: LayerVerdict(verifier=name, decision="skipped", reasons=["layer not active for this run"])
            for name in LAYERS
        }
        if self._envelope is None and not self._secondaries:
            return self._finish(layers, "allow", 0.0, ["ungated baseline: no verification layer active"])

        env_risk = 0.0
        if self._envelope is not None:
            env = self._envelope.verify(incident, action)
            layers["envelope"] = LayerVerdict(
                verifier="envelope", decision=env.decision, risk_score=env.risk_score, reasons=env.reasons
            )
            if env.decision == "block":
                for name in self._secondaries:
                    layers[name] = LayerVerdict(
                        verifier=name,
                        decision="skipped",
                        reasons=["not evaluated: the envelope already blocked"],
                    )
                return self._finish(layers, "block", 1.0, env.reasons)
            env_risk = env.risk_score

        secondary = {name: v.verify(incident, action) for name, v in self._secondaries.items()}
        for name, verdict in secondary.items():
            layers[name] = LayerVerdict(
                verifier=name,
                decision=verdict.decision,
                risk_score=verdict.risk_score,
                reasons=verdict.reasons,
            )
        return self._decide(layers, secondary, env_risk)

    def _decide(
        self, layers: dict[str, LayerVerdict], secondary: dict[str, Verdict], env_risk: float
    ) -> Verdict:
        score = max((v.risk_score for v in secondary.values()), default=env_risk)
        source = max(secondary, key=lambda n: secondary[n].risk_score) if secondary else "envelope"
        if score < self.threshold:
            return self._finish(
                layers, "allow", score, [f"risk {score:.2f} ({source}) is below tau={self.threshold:.2f}"]
            )
        over = {n: v for n, v in secondary.items() if v.risk_score >= self.threshold}
        wants_revise = any(v.decision == "revise" for v in over.values())
        wants_block = any(v.decision == "block" for v in over.values())
        decision = "revise" if wants_revise and not wants_block else "block"
        reasons = [f"risk {score:.2f} ({source}) is at or above tau={self.threshold:.2f}"]
        for verdict in (over or secondary).values():
            reasons.extend(verdict.reasons)
        return self._finish(layers, decision, score, reasons)

    @staticmethod
    def _finish(layers: dict[str, LayerVerdict], decision: str, risk: float, reasons: list[str]) -> Verdict:
        return Verdict(
            decision=decision,
            risk_score=round(min(1.0, max(0.0, risk)), 6),
            reasons=reasons,
            verifier="combined",
            layers=[layers[name] for name in LAYERS],
        )


def build_policy(
    variant: str,
    *,
    threshold: float,
    envelope: EnvelopeVerifier | None = None,
    judge: Verifier | None = None,
    learned: Verifier | None = None,
) -> CombinedPolicy:
    """The five verification variants the eval compares (blueprint §7 baselines):

    none      -- ungated agent (every proposal allowed; the 'diagnosis-recovery gap' reference)
    envelope  -- deterministic gate only
    llm_judge -- envelope + LLM judge (v1)
    learned   -- envelope + learned verifier (v2)
    combined  -- envelope + judge + learned (score = the more cautious of the two)
    """
    if variant not in VARIANTS:
        raise ValueError(f"unknown verifier variant {variant!r}; expected one of {VARIANTS}")
    if variant == "none":
        return CombinedPolicy(None, None, threshold)
    envelope = envelope or EnvelopeVerifier()
    needed = {
        "envelope": [],
        "llm_judge": ["llm_judge"],
        "learned": ["learned"],
        "combined": ["llm_judge", "learned"],
    }[variant]
    available = {"llm_judge": judge, "learned": learned}
    missing = [name for name in needed if available[name] is None]
    if missing:
        raise ValueError(f"verifier variant {variant!r} needs {missing} but it was not provided")
    return CombinedPolicy(envelope, {name: available[name] for name in needed}, threshold)
