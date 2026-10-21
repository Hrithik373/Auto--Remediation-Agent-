# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Learned verifier: calibrated XGBoost estimate of P(destructive), trained per incident fold.
# Model files are written by `make train` and loaded from runs/models/.
"""Learned verifier (v2, blueprint §5, §6.2): calibrated P(destructive) from XGBoost over features.py.

Training protocol -- "split by incident; never leak an incident across splits":
  * Cross-fitting. Incidents are partitioned into K folds (GroupKFold). For each fold, a model is
    trained on the OTHER folds' incidents only. Every incident is therefore scored by a model that
    never saw it -- both for the reported AUC/ECE and later, in the P4 eval runs, where the verifier
    looks up the fold model that held the incident out. Incidents absent from training (new data)
    use a model fit on all incidents.
  * Calibration. Within each training set, an inner GroupKFold yields out-of-fold margins; a Platt
    (logistic) map is fit on those, so the risk score is a probability tau can meaningfully cut.
  * Target: label == "destructive". out_of_envelope rows are excluded -- the deterministic envelope
    owns that class and the learned layer never sees those actions at runtime.

The incident id is used ONLY to pick which cross-fitted model to apply -- it is never a feature.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from xgboost import DMatrix, XGBClassifier

from sentinel.labeling.schema import LabeledAction
from sentinel.schemas.action import ProposedAction
from sentinel.schemas.incident import IncidentContext
from sentinel.schemas.verdict import Verdict
from sentinel.verifier.base import Verifier
from sentinel.verifier.features import TOPOLOGY_FEATURES, extract_features, proposal_text

BUNDLE_VERSION = 1


@dataclass
class FittedModel:
    """TF-IDF (train-only vocabulary) + XGBoost + Platt calibration."""

    tfidf: TfidfVectorizer
    xgb: XGBClassifier
    platt: LogisticRegression
    feature_names: list[str]

    def _matrix(self, structural: np.ndarray, texts: list[str]) -> np.ndarray:
        return np.hstack([structural, self.tfidf.transform(texts).toarray()])

    def margins(self, structural: np.ndarray, texts: list[str]) -> np.ndarray:
        return self.xgb.predict(self._matrix(structural, texts), output_margin=True)

    def predict_proba(self, structural: np.ndarray, texts: list[str]) -> np.ndarray:
        return self.platt.predict_proba(self.margins(structural, texts).reshape(-1, 1))[:, 1]

    def contributions(self, structural: np.ndarray, texts: list[str]) -> np.ndarray:
        dmatrix = DMatrix(self._matrix(structural, texts))
        return self.xgb.get_booster().predict(dmatrix, pred_contribs=True)[:, :-1]  # drop bias column


# -- training -----------------------------------------------------------------------------------


def _xgb(seed: int) -> XGBClassifier:
    return XGBClassifier(
        n_estimators=150,
        max_depth=3,
        learning_rate=0.1,
        subsample=0.9,
        colsample_bytree=0.9,
        min_child_weight=1.0,
        eval_metric="logloss",
        tree_method="hist",
        random_state=seed,
        n_jobs=1,
    )


def _tfidf() -> TfidfVectorizer:
    return TfidfVectorizer(max_features=40, min_df=3, token_pattern=r"(?u)\b[a-z_]{3,}\b", lowercase=True)


def _fit_raw(
    structural: np.ndarray, texts: list[str], y: np.ndarray, seed: int
) -> tuple[TfidfVectorizer, XGBClassifier]:
    tfidf = _tfidf().fit(texts)
    xgb = _xgb(seed).fit(np.hstack([structural, tfidf.transform(texts).toarray()]), y)
    return tfidf, xgb


def _fit_calibrated(
    structural: np.ndarray,
    texts: list[str],
    y: np.ndarray,
    groups: np.ndarray,
    names: list[str],
    seed: int,
    inner_folds: int = 4,
) -> FittedModel:
    """XGB on all given rows; Platt map fit on inner out-of-fold margins (grouped by incident)."""
    oof = np.zeros(len(y))
    for fit_idx, cal_idx in GroupKFold(n_splits=min(inner_folds, len(set(groups)))).split(
        structural, y, groups
    ):
        tfidf, xgb = _fit_raw(structural[fit_idx], [texts[i] for i in fit_idx], y[fit_idx], seed)
        partial = FittedModel(tfidf, xgb, LogisticRegression(), names)
        oof[cal_idx] = partial.margins(structural[cal_idx], [texts[i] for i in cal_idx])
    platt = LogisticRegression().fit(oof.reshape(-1, 1), y)
    tfidf, xgb = _fit_raw(structural, texts, y, seed)
    return FittedModel(tfidf, xgb, platt, names)


def expected_calibration_error(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    ece = 0.0
    for b in range(bins):
        mask = idx == b
        if mask.any():
            ece += mask.mean() * abs(p[mask].mean() - y[mask].mean())
    return float(ece)


def classification_metrics(y: np.ndarray, p: np.ndarray) -> dict:
    out = {
        "n": int(len(y)),
        "positives": int(y.sum()),
        "ece": round(expected_calibration_error(y, p), 4),
        "brier": round(float(brier_score_loss(y, p)), 4),
    }
    out["auc"] = round(float(roc_auc_score(y, p)), 4) if 0 < y.sum() < len(y) else None
    return out


def type_only_baseline(rows: list[LabeledAction], n_folds: int = 5) -> dict:
    """Out-of-fold metrics for a logistic model on action-type one-hots + replicas==0 + enabled==True.

    The reference the learned verifier must beat: if action type alone separates the labels, any
    "learned" result is just a rule restated, and context features add nothing.
    """
    rows = [r for r in rows if r.label != "out_of_envelope"]
    types = sorted({r.action.action_type for r in rows})
    X = np.array(
        [
            [r.action.action_type == t for t in types]
            + [r.action.params.get("replicas") == 0, r.action.params.get("enabled") is True]
            for r in rows
        ],
        dtype=float,
    )
    y = np.array([r.label == "destructive" for r in rows], dtype=int)
    groups = np.array([r.incident_id for r in rows])
    oof = np.zeros(len(y))
    for train_idx, test_idx in GroupKFold(n_splits=n_folds).split(X, y, groups):
        oof[test_idx] = LogisticRegression().fit(X[train_idx], y[train_idx]).predict_proba(X[test_idx])[:, 1]
    return {**classification_metrics(y, oof), "oof_p": oof.round(6).tolist()}


def mixed_label_types(action_types: list[str], y: list[int]) -> set[str]:
    """Action types that occur with BOTH destructive and non-destructive labels -- the rows where the
    type alone cannot decide, i.e. where a verifier has to use context."""
    seen: dict[str, set[int]] = {}
    for t, label in zip(action_types, y):
        seen.setdefault(t, set()).add(label)
    return {t for t, labels in seen.items() if labels == {0, 1}}


def design_matrix(
    rows: list[LabeledAction], incidents: dict[str, IncidentContext], drop: tuple[str, ...] = ()
) -> tuple[np.ndarray, list[str], list[str]]:
    dicts = [extract_features(incidents[r.incident_id], r.action) for r in rows]
    names = sorted(k for k in dicts[0] if k not in drop)
    structural = np.array([[d[n] for n in names] for d in dicts], dtype=float)
    return structural, names, [proposal_text(r.action) for r in rows]


def train_bundle(
    rows: list[LabeledAction],
    incidents: dict[str, IncidentContext],
    *,
    seed: int = 0,
    n_folds: int = 5,
    use_topology: bool = True,
) -> dict:
    """Cross-fitted, calibrated bundle + out-of-fold metrics. See module docstring for the protocol."""
    rows = [r for r in rows if r.label != "out_of_envelope"]
    structural, names, texts = design_matrix(rows, incidents, () if use_topology else TOPOLOGY_FEATURES)
    y = np.array([r.label == "destructive" for r in rows], dtype=int)
    groups = np.array([r.incident_id for r in rows])

    fold_of: dict[str, int] = {}
    fold_models: list[FittedModel] = []
    oof = np.zeros(len(y))
    for k, (train_idx, test_idx) in enumerate(GroupKFold(n_splits=n_folds).split(structural, y, groups)):
        model = _fit_calibrated(
            structural[train_idx], [texts[i] for i in train_idx], y[train_idx], groups[train_idx], names, seed
        )
        oof[test_idx] = model.predict_proba(structural[test_idx], [texts[i] for i in test_idx])
        fold_models.append(model)
        fold_of.update({g: k for g in set(groups[test_idx])})

    full = _fit_calibrated(structural, texts, y, groups, names, seed)
    return {
        "version": BUNDLE_VERSION,
        "seed": seed,
        "n_folds": n_folds,
        "use_topology": use_topology,
        "feature_names": names,
        "fold_of": fold_of,
        "fold_models": fold_models,
        "full_model": full,
        "oof": {
            "incident_id": groups.tolist(),
            "y": y.tolist(),
            "p": oof.round(6).tolist(),
            "action_type": [r.action.action_type for r in rows],
            "provenance": [r.provenance for r in rows],
        },
        "metrics": classification_metrics(y, oof),
    }


# -- inference ----------------------------------------------------------------------------------

_READABLE = {
    "target_in_alert": ("target is named by a firing alert", "target is not named by any firing alert"),
    "target_in_topology": ("target is in the incident topology", "target is not in the incident topology"),
    "target_in_traces": ("target appears in trace spans", "target does not appear in trace spans"),
    "reversible": ("action type is reversible", "action type is not reversible"),
}


def _reason(name: str, value: float) -> str:
    if name in _READABLE:
        return _READABLE[name][0 if value else 1]
    if name.startswith("type=") or name.startswith("scope="):
        key, _, val = name.partition("=")
        return f"{'' if value else 'not '}{key} '{val}'"
    if name == "blast_radius":
        return f"blast radius is {['low', 'medium', 'high'][int(value)]}"
    if name.startswith("target_") and "mentions" in name:
        return f"target appears in {int(value)} {'error ' if 'error' in name else ''}log line(s)"
    return f"{name} = {value:g}"


class LearnedVerifier(Verifier):
    def __init__(
        self, *, model_path: str | Path | None = None, bundle: dict | None = None, max_reasons: int = 3
    ) -> None:
        if bundle is None:
            if model_path is None or not Path(model_path).exists():
                raise FileNotFoundError(f"no learned-verifier model at {model_path}; run `make train` first")
            bundle = joblib.load(model_path)
        if bundle.get("version") != BUNDLE_VERSION:
            raise ValueError(f"learned-verifier bundle version {bundle.get('version')} != {BUNDLE_VERSION}")
        self._bundle = bundle
        self._max_reasons = max_reasons

    def _model_for(self, incident_id: str) -> tuple[FittedModel, str]:
        fold = self._bundle["fold_of"].get(incident_id)
        if fold is None:
            return self._bundle["full_model"], "model fit on all training incidents"
        return self._bundle["fold_models"][fold], f"cross-fitted model (incident held out, fold {fold})"

    def verify(self, incident: IncidentContext, action: ProposedAction) -> Verdict:
        model, which = self._model_for(incident.incident_id)
        feats = extract_features(incident, action)
        structural = np.array([[feats.get(n, 0.0) for n in model.feature_names]], dtype=float)
        texts = [proposal_text(action)]
        risk = float(model.predict_proba(structural, texts)[0])
        contribs = model.contributions(structural, texts)[0][: len(model.feature_names)]
        direction = 1 if risk >= 0.5 else -1
        order = np.argsort(-direction * contribs)
        top = [
            _reason(model.feature_names[i], structural[0, i])
            for i in order[: self._max_reasons]
            if direction * contribs[i] > 0
        ]
        return Verdict(
            decision="block" if risk >= 0.5 else "allow",
            risk_score=round(risk, 6),
            reasons=[f"P(destructive) = {risk:.2f} ({which})", *top],
            verifier="learned",
        )
