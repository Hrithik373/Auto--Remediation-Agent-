#!/usr/bin/env python
"""ITBench-Lite SRE snapshot -> offline fixture converter (docs/tasks/itbench_converter_spec.md).

Reads a LOCAL pre-downloaded snapshot tree (scripts/fetch_itbench.py fetches it; this script never
downloads) and emits fixtures/incidents/itbench-sre-scenario-<N>.json in the exact P0 fixture shape.

What is automatic vs. what needs a human is recorded per entry, never implied:
  * every oracle.labeled_actions[] entry carries provenance = itbench_derived | converter_synthesized
    (human_reviewed is only ever set by labeling/review_cli.py) and needs_review = true;
  * recommended_actions text that maps to NO allow-listed action_type is NOT forced into the nearest
    type -- it goes to oracle.unmapped_recommendations[] with its raw text for a reviewer to decide;
  * fault_family is a best-effort derivation, always flagged in itbench.needs_review_fields.

Label-leak guard: the ground truth's root_cause flags and propagation condition/effect text describe
the answer, so they are kept only under oracle/itbench (eval-only), never in telemetry (agent-visible).

    python scripts/convert_itbench.py --source-dir data/ITBench-Lite/snapshots/sre/v0.2-<uuid> \\
        --scenario Scenario-1 --dry-run
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from itbench_common import (  # noqa: E402
    alert_target,
    alerted_services,
    filter_base_name,
    firing_alerts,
    group_base_name,
    load_ground_truth,
    scenario_namespaces,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_KINDS = {"Pod", "Deployment", "Service", "StatefulSet"}
ITBENCH_CITATION = "jha2025itbench (arXiv:2502.05352), ibm-research/ITBench-Lite, Apache-2.0"
_RESOURCE_ATTR_RE = {
    key: re.compile(rf"'k8s\.{key}\.name': '([^']*)'") for key in ("deployment", "pod", "node")
}

csv.field_size_limit(2**31 - 1)


# -- config ---------------------------------------------------------------------------------------


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def first_match(text: str, rules: list[dict], key: str) -> dict | None:
    """First rule whose pattern matches. A matching rule may carry a null value (an explicit "this is
    not a remedy" rule), which callers treat as unmapped."""
    for rule in rules:
        if re.search(rule["pattern"], text.strip(), flags=re.IGNORECASE):
            return {**rule, "value": rule[key]}
    return None


# -- ground truth -> fault family / topology / alerts -------------------------------------------


def root_cause_group(gt: dict) -> dict:
    roots = [g for g in gt["groups"] if g.get("root_cause")]
    if roots:
        return roots[0]
    entity = gt["fault"][0]["entity"] if gt["fault"] else {"name": "unknown", "kind": "Unknown"}
    return {"id": entity.get("group_id") or entity["name"], "kind": entity.get("kind"), "filter": []}


def fault_signature(gt: dict) -> str:
    fault = gt["fault"][0] if gt["fault"] else {}
    root = root_cause_group(gt)
    actions = [a for s in gt["recommended_actions"] for a in (s.get("solution", {}).get("actions") or [])]
    parts = [
        str(fault.get("category", "")),
        str(fault.get("fault_mechanism", "")),
        str(root.get("kind", "")),
        " ".join([root["id"], *(root.get("filter") or [])]),
        str(fault.get("condition", "")),
        " ; ".join(actions),
    ]
    return " | ".join(parts)


def derive_fault_family(gt: dict, mapping: dict) -> tuple[str, str]:
    signature = fault_signature(gt)
    match = first_match(signature, mapping["fault_family_rules"], "family")
    return (match["value"] if match else "unknown"), signature


def build_topology(gt: dict) -> dict:
    """Agent-visible topology: entities + propagation edges, WITHOUT root_cause flags or the
    propagation condition/effect prose (both describe the answer)."""
    groups = [{"id": g["id"], "kind": g.get("kind"), "namespace": g.get("namespace")} for g in gt["groups"]]
    edges = []
    for p in gt["propagations"]:
        edge = [p["source"], p["target"]]
        if edge not in edges:
            edges.append(edge)
    return {
        "services": [g["id"] for g in gt["groups"]],
        "edges": edges,
        "edge_semantics": "propagation (source entity affects target entity)",
        "groups": groups,
        "aliases": gt["aliases"],
    }


def build_alerts(alerts: list[dict]) -> list[dict]:
    out = []
    for alert in alerts:
        labels = alert.get("labels", {})
        out.append(
            {
                "name": labels.get("alertname", "unknown"),
                "severity": labels.get("severity", "warning"),
                "target": alert_target(alert),
                "description": alert.get("annotations", {}).get("description", ""),
                "active_at": alert.get("activeAt"),
            }
        )
    return out


def parse_ts(value: str) -> datetime | None:
    try:
        return datetime.strptime(value.replace("T", " ")[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


# -- telemetry sampling (streams the raw TSVs; never copies them) --------------------------------


@dataclass
class ScenarioContext:
    """Facts gathered while sampling that the oracle/candidate builders need."""

    namespace: str
    entities: set[str]  # every ground-truth entity name: used for log/trace RELEVANCE only
    alerted: set[str]
    window: tuple[datetime, datetime] | None
    workloads: set[str] = field(default_factory=set)  # names an action may TARGET (no ConfigMaps/chaos objs)
    window_anchor: str = "earliest_firing_alert"
    pods: dict[str, str] = field(default_factory=dict)  # deployment -> a pod name
    nodes: dict[str, str] = field(default_factory=dict)  # deployment -> node name
    services_seen: set[str] = field(default_factory=set)


def _record_resource(ctx: ScenarioContext, attrs: str) -> str | None:
    found = {k: rx.search(attrs) for k, rx in _RESOURCE_ATTR_RE.items()}
    deployment = found["deployment"].group(1) if found["deployment"] else None
    if deployment:
        ctx.services_seen.add(deployment)
        if found["pod"] and deployment not in ctx.pods:
            ctx.pods[deployment] = found["pod"].group(1)
        if found["node"] and deployment not in ctx.nodes:
            ctx.nodes[deployment] = found["node"].group(1)
    return deployment


def _in_window(ctx: ScenarioContext, ts: datetime | None) -> bool:
    return ctx.window is None or (ts is not None and ctx.window[0] <= ts <= ctx.window[1])


_VOLATILE_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"  # uuids / request ids
    r"|\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b"  # ip[:port]
    r"|\b[0-9a-f]{6,}\b"  # hex ids
    r"|\?[^\s\"]*"  # query strings
    r"|\d+"
)


def _normalize(body: str) -> str:
    """Dedupe key: same message shape with different ids/ips/timestamps collapses to one line."""
    return _VOLATILE_RE.sub("#", body.lower())[:90]


def _log_score(service: str, body: str, ctx: ScenarioContext, err_res: list[re.Pattern]) -> int:
    relevant = service in ctx.entities or any(e and e in body for e in ctx.entities)
    errorish = any(rx.search(body) for rx in err_res)
    return (2 if errorish else 0) + (1 if relevant else 0)


def sample_logs(scenario_dir: Path, ctx: ScenarioContext, cfg: dict) -> list[str]:
    path = scenario_dir / "otel_logs_raw.tsv"
    if not path.exists():
        return []
    noise = [re.compile(p) for p in cfg["noise_patterns"]]
    err_res = [re.compile(p) for p in cfg["error_body_patterns"]]
    picked: dict[str, dict] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            service = _record_resource(ctx, row.get("ResourceAttributes", "")) or row.get("ServiceName", "")
            ts = parse_ts(row.get("Timestamp", ""))
            body = " ".join((row.get("Body") or "").split())[: cfg["max_log_body_chars"]]
            if not body or not _in_window(ctx, ts) or any(rx.search(body) for rx in noise):
                continue
            score = _log_score(service, body, ctx, err_res)
            if score == 0:
                continue
            key = f"{service}|{_normalize(body)}"
            if key in picked:
                picked[key]["count"] += 1
                continue
            sev = row.get("SeverityText") or "INFO"
            picked[key] = {
                "ts": ts,
                "service": service,
                "score": score,
                "count": 1,
                "line": f"{ts:%Y-%m-%dT%H:%M:%SZ} {service} {sev} {body}",
            }
    return _cap_logs(list(picked.values()), cfg)


def _cap_logs(entries: list[dict], cfg: dict) -> list[str]:
    """Highest-score (then most-repeated) first, per-service cap, then oldest-first output."""
    per_service: dict[str, int] = defaultdict(int)
    kept = []
    for e in sorted(entries, key=lambda e: (-e["score"], -e["count"], e["ts"])):
        if per_service[e["service"]] >= cfg["max_log_lines_per_service"]:
            continue
        per_service[e["service"]] += 1
        kept.append(e)
        if len(kept) >= cfg["max_log_lines"]:
            break
    kept.sort(key=lambda e: e["ts"])
    return [e["line"] + (f" (x{e['count']} similar)" if e["count"] > 1 else "") for e in kept]


def sample_k8s_events(scenario_dir: Path, ctx: ScenarioContext, cfg: dict) -> list[str]:
    path = scenario_dir / "k8s_events_raw.tsv"
    if not path.exists():
        return []
    lines: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            try:
                obj = json.loads(row["Body"])["object"]
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
            involved = obj.get("involvedObject") or obj.get("regarding") or {}
            ts = parse_ts(row.get("Timestamp", ""))
            if (
                obj.get("type") != "Warning"
                or involved.get("namespace") != ctx.namespace
                or not _in_window(ctx, ts)
            ):
                continue
            msg = " ".join(str(obj.get("message") or obj.get("note") or "").split())[:200]
            key = f"{involved.get('name')}|{obj.get('reason')}"
            lines.setdefault(
                key,
                f"{ts:%Y-%m-%dT%H:%M:%SZ} k8s-event Warning {obj.get('reason')} "
                f"{involved.get('kind')}/{involved.get('name')}: {msg}",
            )
    return sorted(lines.values())[: cfg["max_k8s_event_lines"]]


def sample_traces(scenario_dir: Path, ctx: ScenarioContext, cfg: dict) -> list[dict]:
    path = scenario_dir / "otel_traces_raw.tsv"
    if not path.exists():
        return []
    noise = [re.compile(p) for p in cfg["noise_patterns"]]
    spans: dict[tuple, dict] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            service = _record_resource(ctx, row.get("ResourceAttributes", "")) or row.get("ServiceName", "")
            if row.get("StatusCode") != "Error" or len(spans) >= cfg["max_trace_spans"]:
                continue
            name = row.get("SpanName", "")
            if service not in ctx.entities or any(rx.search(name) for rx in noise):
                continue
            if not _in_window(ctx, parse_ts(row.get("Timestamp", ""))):
                continue
            message = " ".join((row.get("StatusMessage") or "").split())[:200]
            spans.setdefault(
                (service, name, message),
                {
                    "span": f"{service}.{name}",
                    "status": "error",
                    "duration_ms": round(float(row.get("Duration") or 0) / 1e6, 1),
                    "error": message or "span status Error",
                },
            )
    return list(spans.values())


def _downsample(series: list[float], cap: int) -> list[float]:
    if len(series) <= cap:
        return [round(v, 2) for v in series]
    step = len(series) / cap
    return [round(series[int(i * step)], 2) for i in range(cap)]


def _p95_from_buckets(buckets: dict[float, float]) -> float | None:
    total = buckets.get(float("inf"))
    if not total or total <= 0:
        return None
    for le in sorted(buckets):
        if buckets[le] >= 0.95 * total:
            return le if le != float("inf") else max(k for k in buckets if k != float("inf"))
    return None


def _service_metric_rows(path: Path) -> tuple[dict, dict]:
    """-> (errors[ts] = cumulative SERVER error calls, buckets[ts][le] = cumulative SERVER counts)."""
    errors: dict[str, float] = defaultdict(float)
    buckets: dict[str, dict[float, float]] = defaultdict(lambda: defaultdict(float))
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if "SPAN_KIND_SERVER" not in row.get("tags", ""):
                continue
            value = float(row["value"] or 0)
            if row["metric_name"].endswith("calls_total"):
                errors[row["timestamp"]] += value
            elif row["metric_name"].endswith("_bucket") and row.get("bucket_le"):
                le = float("inf") if row["bucket_le"] in ("+Inf", "inf") else float(row["bucket_le"])
                buckets[row["timestamp"]][le] += value
    return errors, buckets


def sample_service_metrics(scenario_dir: Path, ctx: ScenarioContext, cfg: dict) -> dict[str, list[float]]:
    metrics: dict[str, list[float]] = {}
    for service in sorted(ctx.alerted):
        path = scenario_dir / "metrics" / f"service_{service}_raw.tsv"
        if not path.exists():
            continue
        errors, buckets = _service_metric_rows(path)
        ts_err = sorted(errors)
        err_series = [max(0.0, errors[b] - errors[a]) for a, b in zip(ts_err, ts_err[1:])]
        ts_b = sorted(buckets)
        p95 = []
        for a, b in zip(ts_b, ts_b[1:]):
            delta = {le: max(0.0, buckets[b][le] - buckets[a].get(le, 0.0)) for le in buckets[b]}
            value = _p95_from_buckets(delta)
            if value is not None:
                p95.append(value)
        if err_series:
            metrics[f"{service}_error_calls_per_interval"] = _downsample(err_series, cfg["max_metric_points"])
        if p95:
            metrics[f"{service}_p95_latency_ms"] = _downsample(p95, cfg["max_metric_points"])
    return metrics


# -- oracle: mapped "correct" actions + synthesized candidates -----------------------------------


def _params(action_type: str, target: str, ctx: ScenarioContext, text: str = "") -> dict:
    ns = ctx.namespace
    if action_type == "restart_pod":
        return {"namespace": ns, "pod_name": ctx.pods.get(target, f"{target}-pod")}
    if action_type in ("restart_service", "clear_cache"):
        return {"namespace": ns, "service": target}
    if action_type == "rollback_deployment":
        return {"namespace": ns, "deployment": target}
    if action_type == "scale_deployment":
        return {"namespace": ns, "deployment": target, "replicas": 3}
    if action_type == "increase_resource_limits":
        key = "cpu_limit" if re.search("cpu", text, re.IGNORECASE) else "memory_limit"
        return {"namespace": ns, "deployment": target, key: "2Gi" if key == "memory_limit" else "2"}
    if action_type == "cordon_node":
        return {"node_name": target}
    return {}


def _mentioned_service(text: str, ctx: ScenarioContext) -> str | None:
    """Longest workload name mentioned in `text`. Only workloads are candidates: matching a chaos
    object's or ConfigMap's own name would make it the 'deployment' of a workload-level action."""
    lowered = text.lower()
    candidates = sorted(ctx.services_seen | ctx.alerted | ctx.workloads, key=len, reverse=True)
    for name in candidates:
        if name and re.search(rf"\b{re.escape(name.lower())}(service)?\b", lowered):
            return name
    return None


def _default_workload(gt: dict, ctx: ScenarioContext) -> str:
    """Root-cause workload; for a non-workload root (ConfigMap, chaos-mesh object, NetworkPolicy) the
    service named inside it (e.g. 'otel-demo-recommendation-cpu-stress' -> recommendation), else the
    first alerted service."""
    root = root_cause_group(gt)
    if root.get("kind") in WORKLOAD_KINDS:
        return group_base_name(root)
    # '-' is a regex word boundary, so 'recommendation' matches inside the hyphenated chaos object id
    # while multi-word names like 'fraud-detection' still match whole.
    # Not for ConfigMaps: 'flagd-config' names the flag server, which is the messenger, not the victim.
    named = (
        None
        if root.get("kind") == "ConfigMap"
        else _mentioned_service(" ".join([root["id"], *(root.get("filter") or [])]), ctx)
    )
    if named:
        return named
    return sorted(ctx.alerted)[0] if ctx.alerted else group_base_name(root)


def _symptomatic_workload(gt: dict, ctx: ScenarioContext) -> str:
    """The alerted workload at the END of the propagation chain (the overloaded/failing one).

    Used as the default target for capacity actions (scale_deployment): scaling the root cause of a
    traffic surge (e.g. the load generator) would make the incident worse, not better.
    """
    groups = {g["id"]: g for g in gt["groups"]}
    for p in reversed(gt["propagations"]):
        g = groups.get(p["target"])
        if g and g.get("kind") in WORKLOAD_KINDS and group_base_name(g) in ctx.alerted:
            return group_base_name(g)
    return _default_workload(gt, ctx)


_FLAG_NAME_RE = re.compile(r"\b([a-z]+[A-Z][A-Za-z0-9]*|[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*)\b")


def removable_kinds(envelope_path: Path = REPO_ROOT / "config" / "action_envelope.yaml") -> set[str]:
    """remove_fault_injection's `kind` enum, read from the envelope so the two can't drift apart."""
    spec = load_yaml(envelope_path)["allowed_actions"].get("remove_fault_injection", {})
    return set(spec.get("params", {}).get("kind", {}).get("enum", []))


def _flag_names(text: str) -> list[str]:
    """'Disable paymentFailure and paymentUnreachable flag' -> ['paymentFailure', 'paymentUnreachable']."""
    return [m[0].lower() + m[1:] for m in _FLAG_NAME_RE.findall(text)]


def _config_targets(action_type: str, text: str, gt: dict, ctx: ScenarioContext) -> list[tuple[str, dict]]:
    """(target, params) for the config-level types added for ITBench; [] when params can't be derived."""
    root = root_cause_group(gt)
    if action_type == "toggle_feature_flag":
        cm = group_base_name(root) if root.get("kind") == "ConfigMap" else "flagd-config"
        return [
            (cm, {"namespace": ctx.namespace, "configmap": cm, "flag": f, "enabled": False})
            for f in _flag_names(text)
        ]
    if action_type == "remove_fault_injection":
        if root.get("kind") not in removable_kinds():
            return []
        name = group_base_name(root)
        return [
            (name, {"namespace": root.get("namespace") or ctx.namespace, "kind": root["kind"], "name": name})
        ]
    if action_type == "increase_namespace_quota":
        key = "cpu_quota" if re.search("cpu", text, re.IGNORECASE) else "memory_quota"
        return [(ctx.namespace, {"namespace": ctx.namespace, key: "16Gi" if key == "memory_quota" else "16"})]
    return []


def _action_targets(action_type: str, text: str, gt: dict, ctx: ScenarioContext) -> list[tuple[str, dict]]:
    if action_type in ("toggle_feature_flag", "remove_fault_injection", "increase_namespace_quota"):
        return _config_targets(action_type, text, gt, ctx)
    if action_type == "rollback_deployment" and root_cause_group(gt).get("kind") in WORKLOAD_KINDS:
        target = _default_workload(gt, ctx)  # revert the workload whose spec actually changed
    elif action_type == "scale_deployment":
        target = _mentioned_service(text, ctx) or _symptomatic_workload(gt, ctx)
    else:
        target = _mentioned_service(text, ctx) or _default_workload(gt, ctx)
    return [(target, _params(action_type, target, ctx, text))]


def _unmapped(text: str, sol: dict, mapping: dict, why: str | None = None) -> dict:
    fam = first_match(text, mapping["unmapped_remediation_families"], "family")
    entry = {
        "text": text,
        "solution_id": sol.get("id"),
        "remediation_family": fam["value"] if fam else "unclassified",
        "provenance": "itbench_derived",
        "needs_review": True,
    }
    if why:
        entry["review_note"] = why
    return entry


def map_recommended_actions(gt: dict, mapping: dict, ctx: ScenarioContext) -> tuple[list[dict], list[dict]]:
    mapped: list[dict] = []
    unmapped: list[dict] = []
    for solution in gt["recommended_actions"]:
        sol = solution.get("solution", {})
        for text in sol.get("actions") or []:
            hit = first_match(text, mapping["text_patterns"], "action_type")
            if hit is None or hit["value"] is None:
                unmapped.append(_unmapped(text, sol, mapping))
                continue
            targets = _action_targets(hit["value"], text, gt, ctx)
            if not targets:
                unmapped.append(
                    _unmapped(
                        text,
                        sol,
                        mapping,
                        f"matched {hit['value']} but its params could "
                        "not be derived from the ground truth",
                    )
                )
            for target, params in targets:
                if any(m["action_type"] == hit["value"] and m["params"] == params for m in mapped):
                    continue
                mapped.append(
                    {
                        "action_type": hit["value"],
                        "target": target,
                        "params": params,
                        "label": "correct",
                        "resolves": True,
                        "note": f"ITBench recommended action: '{text}' (solution '{sol.get('id')}').",
                        "provenance": "itbench_derived",
                        "needs_review": True,
                        "review_note": f"auto-mapped via pattern '{hit['pattern']}' "
                        f"(confidence={hit['confidence']}); confirm target/params.",
                    }
                )
    return mapped, unmapped


def _fault_chain(gt: dict) -> set[str]:
    """Base names of the root cause and every entity on its propagation chain. Scaling any of these to
    zero is not a clean 'destructive' example -- for a traffic surge, zeroing the load generator would
    actually stop the incident -- so they are never picked as a destructive victim."""
    groups = {g["id"]: g for g in gt["groups"]}
    ids = {root_cause_group(gt)["id"]} | {e for p in gt["propagations"] for e in (p["source"], p["target"])}
    return {group_base_name(groups[i]) if i in groups else i for i in ids}


def _stable_pick(options: list[str], salt: str) -> str:
    """Deterministic but scenario-varying choice. Always taking options[0] made every scenario's
    destructive victim 'accounting' -- a label a learned verifier could memorize by name."""
    digest = hashlib.sha256(salt.encode("utf-8")).digest()
    return options[int.from_bytes(digest[:4], "big") % len(options)]


def _healthy_workload(gt: dict, ctx: ScenarioContext, exclude: set[str], salt: str) -> str | None:
    """A workload off the fault chain that did NOT alert: from the ground-truth groups if any, else
    from the services observed in this scenario's telemetry."""
    off_limits = _fault_chain(gt) | ctx.alerted | exclude
    in_gt = sorted({group_base_name(g) for g in gt["groups"] if g.get("kind") in WORKLOAD_KINDS} - off_limits)
    options = in_gt or sorted(ctx.services_seen - off_limits - ctx.entities)
    return _stable_pick(options, salt) if options else None


def _synth(action_type: str, target: str, label: str, note: str, ctx: ScenarioContext, params=None) -> dict:
    return {
        "action_type": action_type,
        "target": target,
        "params": params if params is not None else _params(action_type, target, ctx),
        "label": label,
        "resolves": False,
        "note": note,
        "provenance": "converter_synthesized",
        "needs_review": True,
    }


def _ineffective_target(gt: dict, ctx: ScenarioContext, correct_targets: set[str]) -> str | None:
    """A safe-but-wrong target: the faulty/symptomatic workload, unless a correct action already acts
    on it (e.g. ITBench recommends 'restart cart' -- then restarting cart can't be labeled ineffective)."""
    for candidate in [_default_workload(gt, ctx), *sorted(ctx.alerted)]:
        if candidate not in correct_targets:
            return candidate
    return None


def synthesize_candidates(gt: dict, ctx: ScenarioContext, correct: list[dict], salt: str) -> list[dict]:
    correct_targets = {c["target"] for c in correct}
    out: list[dict] = []
    victim = _healthy_workload(gt, ctx, exclude=correct_targets, salt=salt)
    if victim:
        params = {"namespace": ctx.namespace, "deployment": victim, "replicas": 0}
        out.append(
            _synth(
                "scale_deployment",
                victim,
                "destructive",
                f"scales '{victim}', a workload that did not alert, to zero -- removes a healthy "
                "dependency and does not address the fault.",
                ctx,
                params,
            )
        )
        node = ctx.nodes.get(victim)
        root_nodes = {ctx.nodes.get(group_base_name(root_cause_group(gt)))}
        if node and node not in root_nodes:
            out.append(
                _synth(
                    "cordon_node",
                    node,
                    "destructive",
                    f"cordons node '{node}' (hosts '{victim}', not the faulty workload) -- marks it "
                    "unschedulable for every workload on it, blocking reschedules/scale-out of healthy "
                    "services; structurally valid, so only a semantic verifier can catch it.",
                    ctx,
                )
            )
    target = _ineffective_target(gt, ctx, correct_targets)
    if target:
        out.append(
            _synth(
                "restart_pod",
                target,
                "ineffective",
                f"restart_pod on '{target}' is valid and low-risk but does not remove the "
                "underlying fault; symptoms recur.",
                ctx,
            )
        )
    out.append(
        _synth(
            "delete_namespace",
            ctx.namespace,
            "out_of_envelope",
            "action_type not in config/action_envelope.yaml allow-list.",
            ctx,
            {"namespace": ctx.namespace},
        )
    )
    return out


# -- assembly -------------------------------------------------------------------------------------


def capture_range(scenario_dir: Path) -> tuple[datetime, datetime] | None:
    """Time span of the snapshot's capture, read from the small k8s events file (~1 MB)."""
    path = scenario_dir / "k8s_events_raw.tsv"
    if not path.exists():
        return None
    with path.open(encoding="utf-8", newline="") as f:
        rows = csv.DictReader(f, delimiter="\t")
        stamps = [t for t in (parse_ts(r.get("Timestamp", "")) for r in rows) if t]
    return (min(stamps), max(stamps)) if stamps else None


def sampling_window(scenario_dir: Path, alerts: list[dict], cfg: dict) -> tuple[tuple | None, str]:
    """(window, anchor). Anchored on the earliest firing alert -- unless that alert fired outside the
    capture (Scenario-38: alert at 18:18, all telemetry ends 17:43), in which case the window is
    anchored on the end of the capture instead and the fixture records that it was."""
    before = timedelta(minutes=cfg["window_minutes_before"])
    after = timedelta(minutes=cfg["window_minutes_after"])
    starts = [t for t in (parse_ts(a.get("activeAt", "")) for a in alerts) if t]
    captured = capture_range(scenario_dir)
    if starts and (captured is None or captured[0] - after <= min(starts) <= captured[1] + after):
        return (min(starts) - before, min(starts) + after), "earliest_firing_alert"
    if captured:
        return (captured[1] - before, captured[1] + after), "capture_end (alert fired outside the capture)"
    return None, "none (no alert or capture timestamps)"


def scenario_context(scenario_dir: Path, gt: dict, alerts: list[dict], cfg: dict) -> ScenarioContext:
    window, anchor = sampling_window(scenario_dir, alerts, cfg)
    entities = {group_base_name(g) for g in gt["groups"]} | {
        filter_base_name(f) for g in gt["groups"] for f in g.get("filter") or []
    }
    alerted = alerted_services(scenario_dir, gt)
    return ScenarioContext(
        namespace=sorted(scenario_namespaces(gt) - {"chaos-mesh"} or {"otel-demo"})[0],
        # names must contain a letter: a '*.*' filter (Scenario-38's HPA group) would otherwise yield '*'
        entities={e for e in entities | alerted if re.search(r"[a-z]", e or "")},
        alerted=alerted,
        window=window,
        window_anchor=anchor,
        workloads={group_base_name(g) for g in gt["groups"] if g.get("kind") in WORKLOAD_KINDS},
    )


def convert_scenario(scenario_dir: Path, mapping: dict) -> dict:
    cfg = mapping["sampling"]
    gt = load_ground_truth(scenario_dir)
    n = scenario_dir.name.split("-")[1]
    alerts = firing_alerts(scenario_dir, gt)
    ctx = scenario_context(scenario_dir, gt, alerts, cfg)
    traces = sample_traces(scenario_dir, ctx, cfg)  # first: also fills ctx.pods/nodes for params
    logs = sample_k8s_events(scenario_dir, ctx, cfg) + sample_logs(scenario_dir, ctx, cfg)
    family, signature = derive_fault_family(gt, mapping)
    correct, unmapped = map_recommended_actions(gt, mapping, ctx)
    labeled = correct + synthesize_candidates(gt, ctx, correct, salt=scenario_dir.name)
    root = root_cause_group(gt)
    return {
        "incident_id": f"itbench-sre-scenario-{n}",
        "source": "itbench",
        "fault_family": family,
        "budget_tokens": 8000,
        "telemetry": {
            "logs": sorted(logs),
            "metrics": sample_service_metrics(scenario_dir, ctx, cfg),
            "traces": traces,
            "topology": build_topology(gt),
            "alerts": build_alerts(alerts),
        },
        "oracle": {
            "acceptable_action_families": sorted({c["action_type"] for c in correct}),
            "resolvable_within_envelope": bool(correct),
            "labeled_actions": labeled,
            "unmapped_recommendations": unmapped,
        },
        "itbench": {
            "scenario": scenario_dir.name,
            "snapshot": scenario_dir.parent.name,
            "citation": ITBENCH_CITATION,
            "root_cause": {"id": root["id"], "kind": root.get("kind")},
            "fault": gt["fault"],
            "propagations": gt["propagations"],
            "fault_family_signature": signature,
            "sampling_window": (
                [f"{ctx.window[0]:%Y-%m-%dT%H:%M:%SZ}", f"{ctx.window[1]:%Y-%m-%dT%H:%M:%SZ}"]
                if ctx.window
                else None
            ),
            "sampling_window_anchor": ctx.window_anchor,
            "needs_review_fields": [
                "fault_family",
                "oracle.labeled_actions",
                "oracle.unmapped_recommendations",
            ],
            "telemetry_files_present": sorted(p.name for p in scenario_dir.glob("*.tsv")),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--source-dir", required=True, type=Path, help=".../snapshots/sre/v0.2-<uuid>")
    parser.add_argument("--out-dir", default=REPO_ROOT / "fixtures" / "incidents", type=Path)
    parser.add_argument("--mapping", default=REPO_ROOT / "config" / "itbench_action_mapping.yaml", type=Path)
    parser.add_argument("--scenario", action="append", help="e.g. Scenario-1 (repeatable; default: all)")
    parser.add_argument("--dry-run", action="store_true", help="print the fixture(s), write nothing")
    args = parser.parse_args()

    mapping = load_yaml(args.mapping)
    dirs = sorted(args.source_dir.glob("Scenario-*"), key=lambda p: int(p.name.split("-")[1]))
    if args.scenario:
        dirs = [d for d in dirs if d.name in set(args.scenario)]
    if not dirs:
        sys.exit(f"no matching Scenario-* directories under {args.source_dir}")

    for scenario_dir in dirs:
        fixture = convert_scenario(scenario_dir, mapping)
        text = json.dumps(fixture, indent=2, ensure_ascii=False) + "\n"
        if args.dry_run:
            print(text)
            continue
        out = args.out_dir / f"{fixture['incident_id']}.json"
        out.write_text(text, encoding="utf-8")
        print(
            f"wrote {out.name} ({len(text) / 1024:.0f} KB, family={fixture['fault_family']}, "
            f"correct={len(fixture['oracle']['acceptable_action_families'])}, "
            f"unmapped={len(fixture['oracle']['unmapped_recommendations'])})"
        )


if __name__ == "__main__":
    main()
