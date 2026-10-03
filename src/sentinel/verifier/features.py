"""Feature extraction for the learned verifier (blueprint §6.2).

Inputs are ONLY what a verifier may legitimately see: the incident's observable telemetry and the
proposed action (+ the envelope's static description of the action type). Never the oracle, the
fault_family, or the incident id.

  * action:   action_type one-hot, scope one-hot, blast radius, reversibility, replicas.
  * linkage:  does the telemetry implicate the target? (alert targets, log/trace mentions, topology
              membership and degree) -- "acting on something nothing points at" is the core signal.
  * context:  #alerts, max alert severity, #anomalous metric series, topology size.
  * text:     TF-IDF over the proposal's rationale/predicted_effect (fit in learned.py, train-only).

Agent-confidence features (token logprobs / self-reported confidence) are not available from the
current agents and are omitted rather than faked.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from sentinel.schemas.action import ProposedAction
from sentinel.schemas.incident import IncidentContext

_ENVELOPE_PATH = Path(__file__).resolve().parents[3] / "config" / "action_envelope.yaml"
_SEVERITY = {"info": 0, "warning": 1, "high": 2, "critical": 3}
_BLAST = {"low": 0, "medium": 1, "high": 2}
_ERRORISH = re.compile(r"(?i)error|fatal|fail|timeout|refused|exception|oom|crash|evict|\b5\d\d\b")


@lru_cache(maxsize=1)
def envelope_spec(path: str = str(_ENVELOPE_PATH)) -> dict:
    with Path(path).open(encoding="utf-8") as f:
        return yaml.safe_load(f)["allowed_actions"]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _mentions(target: str, text: str) -> bool:
    """Loose match: 'payments-api' matches 'payments-api-7d9f-xk2z' and 'payments_api'."""
    t = _norm(target)
    return bool(t) and t in _norm(text)


def _topology_entities(topology: dict) -> list[str]:
    return [str(s) for s in topology.get("services", [])]


def _degree(target: str, topology: dict) -> tuple[int, int]:
    """(in_degree, out_degree) of the entity the target names, matched loosely."""
    ins = outs = 0
    for edge in topology.get("edges", []):
        if len(edge) == 2:
            src, dst = str(edge[0]), str(edge[1])
            outs += _mentions(target, src) or _mentions(src, target)
            ins += _mentions(target, dst) or _mentions(dst, target)
    return ins, outs


def _anomalous_series(metrics: dict[str, list[float]]) -> int:
    count = 0
    for series in metrics.values():
        if len(series) >= 2:
            lo, hi = min(series), max(series)
            count += (hi - lo) / (abs(lo) + 1.0) > 1.0
    return count


def _action_features(action: ProposedAction) -> dict[str, float]:
    spec = envelope_spec().get(action.action_type, {})
    feats: dict[str, float] = {f"type={t}": float(action.action_type == t) for t in envelope_spec()}
    scopes = sorted({s.get("scope", "?") for s in envelope_spec().values()})
    feats.update({f"scope={s}": float(spec.get("scope") == s) for s in scopes})
    replicas = action.params.get("replicas")
    enabled = action.params.get("enabled")
    feats.update(
        {
            "param_enabled": (
                {True: 1.0, False: 0.0}.get(enabled, -1.0) if isinstance(enabled, bool) else -1.0
            ),
            "blast_radius": float(_BLAST.get(spec.get("blast_radius", "high"), 2)),
            "reversible": float(bool(spec.get("reversible", False))),
            "has_replicas": float(isinstance(replicas, int)),
            "replicas": float(replicas) if isinstance(replicas, int) else -1.0,
            "n_params": float(len(action.params)),
        }
    )
    return feats


def _linkage_features(incident: IncidentContext, target: str) -> dict[str, float]:
    t = incident.telemetry
    alert_targets = [str(a.get("target", "")) for a in t.alerts]
    log_hits = [line for line in t.logs if _mentions(target, line)]
    ins, outs = _degree(target, t.topology)
    return {
        "target_in_alert": float(
            any(_mentions(target, a) or _mentions(a, target) for a in alert_targets if a)
        ),
        "target_in_topology": float(
            any(_mentions(target, e) or _mentions(e, target) for e in _topology_entities(t.topology))
        ),
        "target_log_mentions": float(len(log_hits)),
        "target_error_log_mentions": float(sum(bool(_ERRORISH.search(line)) for line in log_hits)),
        "target_log_share": len(log_hits) / max(1, len(t.logs)),
        "target_in_traces": float(any(_mentions(target, str(span)) for span in t.traces)),
        "target_in_degree": float(ins),
        "target_out_degree": float(outs),
    }


def _context_features(incident: IncidentContext) -> dict[str, float]:
    t = incident.telemetry
    severities = [_SEVERITY.get(str(a.get("severity", "warning")).lower(), 1) for a in t.alerts]
    return {
        "n_alerts": float(len(t.alerts)),
        "max_alert_severity": float(max(severities, default=0)),
        "n_anomalous_metrics": float(_anomalous_series(t.metrics)),
        "n_topology_entities": float(len(_topology_entities(t.topology))),
        "n_log_lines": float(len(t.logs)),
    }


def extract_features(incident: IncidentContext, action: ProposedAction) -> dict[str, float]:
    """Structural features (everything except the TF-IDF text block). Keys are stable across calls."""
    return {
        **_action_features(action),
        **_linkage_features(incident, action.target),
        **_context_features(incident),
    }


TOPOLOGY_FEATURES = ("target_in_topology", "target_in_degree", "target_out_degree", "n_topology_entities")


def proposal_text(action: ProposedAction) -> str:
    return f"{action.rationale} {action.predicted_effect}"
