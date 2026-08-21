"""Learned verifier (v2, XGBoost) — Phase P3. Not implemented yet; see PROGRESS.md.

Intended behavior (blueprint §5, §6.2): a calibrated risk score over features.py's action/context/
agent-confidence features, trained on labeling/oracle_labeler.py output, split by incident (never
leak an incident across train/val/test).
"""

from __future__ import annotations

from pathlib import Path

from sentinel.schemas.action import ProposedAction
from sentinel.schemas.incident import IncidentContext
from sentinel.schemas.verdict import Verdict
from sentinel.verifier.base import Verifier


class LearnedVerifier(Verifier):
    def __init__(self, *, model_path: str | Path | None = None) -> None:
        self._model_path = Path(model_path) if model_path else None
        self._model = None  # TODO(P3): load a trained xgboost.Booster

    def verify(self, incident: IncidentContext, action: ProposedAction) -> Verdict:
        raise NotImplementedError(
            "LearnedVerifier is Phase P3 work. See ARCHITECTURE_BLUEPRINT.md §5, §6.2, §8."
        )
