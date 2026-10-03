# Task spec: ITBench-snapshot → fixture converter

> Status: **implemented** — `scripts/fetch_itbench.py`, `scripts/convert_itbench.py`,
> `config/itbench_action_mapping.yaml`, tests in `tests/test_convert_itbench.py` +
> `tests/test_itbench_fixtures.py`. Grows `fixtures/incidents/` from 6 hand-built incidents to 41.
>
> **Deviations from this spec, decided during implementation (with reasons):**
> 1. *Size.* The SRE tree is ~31 GB, not "several GB" (~18 GB is per-pod/per-service metrics).
>    `fetch_itbench.py` downloads only what the converter reads (~14 GB): logs, traces, events, and the
>    `service_<name>_raw.tsv` span-metric files for services that alerted. `metrics/` is per-pod/per-
>    service span-metric TSVs, not Prometheus exposition files; the converter derives per-interval
>    error-call counts and p95 latency from them.
> 2. *Envelope extended.* Only 7/35 scenarios had any remedy expressible in the original 7 action types —
>    most ITBench fixes are config-level (feature flags, chaos experiments, quotas). Added
>    `toggle_feature_flag`, `remove_fault_injection` (with a `kind` enum gate — the envelope gained `enum`
>    param validation for it), and `increase_namespace_quota` to `config/action_envelope.yaml`. Env-var /
>    image / command / node-selector fixes in a deployment map to the existing `rollback_deployment`
>    (medium confidence). Result: 34/35 resolvable within the envelope; Scenario-38 (investigation-only
>    remedies) is a "should escalate" case.
> 3. *Unmapped remedies* go to `oracle.unmapped_recommendations[]` instead of a `labeled_actions[]` entry
>    with `action_type: null` — a null type would fail `ProposedAction` validation wherever fixtures are
>    replayed (e.g. `tests/test_envelope.py`).
> 4. *Extra destructive candidate.* Besides scale-to-zero (always caught by the envelope's `replicas >= 1`
>    floor), the converter synthesizes `cordon_node` on a node hosting an off-chain workload, so the
>    "envelope passes it, only a semantic verifier catches it" case exists in the ITBench set too.
> 5. *Leak guard.* `groups[].root_cause` and propagation `condition`/`effect` prose describe the answer,
>    so they are kept only under the fixture's eval-only `itbench` block, never in `telemetry`.
> 6. *Destructive victims exclude the fault chain.* Scaling an on-chain entity to zero is not cleanly
>    destructive (zeroing a surge's load generator ends the incident), so victims are off-chain workloads.

---

## 0. What ITBench-Lite actually ships (verified, not assumed)

Source: [`ibm-research/ITBench-Lite`](https://huggingface.co/datasets/ibm-research/ITBench-Lite) on
Hugging Face. **Apache 2.0**, citation required:

```bibtex
@misc{jha2025itbench,
  title={ITBench: Evaluating AI Agents across Diverse Real-World IT Automation Tasks},
  author={Jha, Saurabh and Arora, Rohan and Watanabe, Yuji and others},
  year={2025},
  eprint={2502.05352},
  archivePrefix={arXiv},
  primaryClass={cs.AI}
}
```

65 scenarios total across three domains; we only want the **35 SRE scenarios** (FinOps/CISO are out
of scope — this project remediates operational incidents, not compliance/cost tasks). Layout:

```
snapshots/sre/v0.2-<uuid>/Scenario-<N>/
├── ground_truth.yaml        # ~2 KB  — fault, alerts, groups, aliases, propagations, recommended_actions
├── k8s_events_raw.tsv       # ~1 MB  — Kubernetes events
├── k8s_objects_raw.tsv      # ~44 MB — Kubernetes resource states (pods/services/deployments)
├── otel_logs_raw.tsv        # ~281 MB — OpenTelemetry logs
├── otel_traces_raw.tsv      # ~163 MB — OpenTelemetry traces
├── alerts/                  # JSON — time-series alert snapshots
└── metrics/                 # Prometheus format
```

Scenario IDs are non-contiguous (`Scenario-1, 2, 4, 5, 6, 7, 8, 9, 11, ... 105`) — 35 folders, not a
clean 1..35 range. The whole `snapshots/` tree is **31 GB**; SRE-only is still on the order of several
GB because of the raw otel dumps. **Do not check raw ITBench data into this git repo** — only the
compacted fixture JSON (same shape as the existing 6) is committed.

### `ground_truth.yaml`'s actual schema (fetched and confirmed from Scenario-1)

```yaml
fault:
  - entity: {name: load-generator-pod-1, group_id: load-generator-pod-1, kind: Pod}
    condition: To be specified
    category: Change            # <- coarse, not a clean fault-family taxonomy
    fault_mechanism: custom      # <- ditto
alerts:
  - id: RequestErrorRate
    group_id: frontend-proxy-service-1
    metadata: {description: "Error rate is above threshold for frontend-proxy service"}
groups:                          # <- topology building blocks: entities + their k8s filters
  - id: frontend-proxy-pod-1
    kind: Pod
    namespace: otel-demo
    filter: ["frontend-proxy-.*"]
    root_cause: true             # <- marks the ground-truth faulty entity
aliases: [[...]]                 # <- entity-group equivalence sets
propagations:                    # <- causal chain: source entity -> target entity, condition, effect
  - {source: ..., target: ..., condition: "...", effect: "..."}
recommended_actions:             # <- FREE TEXT, not our action_type/target/params shape
  - solution: {id: set_up_autoscaler, actions: ["set up autoscaler"]}
```

**This is the crux of the converter, and the reason it's a task spec and not a five-line script:**
ITBench gives us a real fault, a real topology, and a real root cause — but it does **not** give us
`fault_family`, `action_type`, or the `correct`/`ineffective`/`destructive`/`out_of_envelope` taxonomy
our fixtures need. Those have to be *derived*, and derivation needs a human-reviewable mapping layer,
not a blind auto-label. Don't let the converter claim more automation than it delivers — that's the
same overclaiming trap the P0 envelope-coverage note called out.

---

## 1. What the converter must produce, and what it must NOT claim to produce automatically

For each SRE scenario, emit `fixtures/incidents/itbench-sre-scenario-<N>.json` in the **exact existing
fixture schema** (see any of the 6 P0 fixtures) with these provenance rules:

| Field | Source | Automation level |
|---|---|---|
| `incident_id` | `itbench-sre-scenario-<N>` (must match filename stem — `OfflineEnvAdapter` doesn't enforce this at load time, only at lookup, so get it right here) | fully automatic |
| `source` | `"itbench"` | fully automatic — `IncidentContext.source`'s Literal already includes `"itbench"` (schemas/incident.py), no schema change needed |
| `fault_family` | best-effort from `fault[].category` + `fault_mechanism` + root-cause entity `kind` | **auto-derived, flagged `needs_review`** — ITBench's category/mechanism fields are too coarse to trust unreviewed |
| `telemetry.topology` | `groups` + `aliases` + `propagations` in `ground_truth.yaml` | fully automatic — this part of ITBench's schema is already exactly what our `Telemetry.topology` dict wants |
| `telemetry.alerts` | `alerts/` JSON, reshaped to our `alerts: list[dict]` | fully automatic |
| `telemetry.logs` | sampled from `otel_logs_raw.tsv` (see §2 — do not copy the raw file) | automatic sampling, **not** human-reviewed (logs are supporting context, not a label) |
| `telemetry.metrics` | sampled from `metrics/` (see §2) | automatic sampling |
| `telemetry.traces` | sampled from `otel_traces_raw.tsv` (see §2) | automatic sampling |
| `oracle.labeled_actions[]` where `label: "correct"` | mapped from `recommended_actions[].solution.actions` free text via a small curated keyword→`action_type` lookup (§3) | **auto-mapped, flagged `needs_review`** when confidence is low or no allow-listed action_type matches at all |
| `oracle.labeled_actions[]` where `label` in `{ineffective, destructive, out_of_envelope}` | ITBench provides **none of these** — the converter synthesizes candidates from a small fixed rule set (§3) | **always flagged `needs_review`** — these are converter-authored, not benchmark ground truth |

Every `labeled_actions[]` entry gets a new `"provenance"` key: `"itbench_derived"`,
`"converter_synthesized"`, or `"human_reviewed"` (the last one only ever set by a human running
`labeling/review_cli.py`, Phase P3 — this converter never sets it). This is exactly the "document the
inter-step of oracle-derived vs human-reviewed labels" instruction from
[ARCHITECTURE_BLUEPRINT.md §6.1](../../ARCHITECTURE_BLUEPRINT.md#61-label-taxonomy--what-unsafe-action-means)
— the converter's whole job is to get that provenance trail *started*, not to finish it unsupervised.

## 2. Telemetry sampling (do not embed raw files)

The raw per-scenario files are 200–450 MB combined; our existing fixtures are a few KB each. Sample,
don't copy:

- **logs**: from `otel_logs_raw.tsv`, take lines within a ±10 minute window of the earliest
  `alerts/` firing timestamp that either (a) mention the root-cause entity's name/filter pattern, or
  (b) are `ERROR`/`WARN` severity. Cap at 200 lines, oldest-first.
- **metrics**: from `metrics/` (Prometheus format), keep only the series referenced by the fired
  alerts' `group_id`s (resolve via `groups[]`), downsampled to ≤50 points per series.
- **traces**: from `otel_traces_raw.tsv`, keep ≤10 spans with `status=error` touching the root-cause
  entity or anything on its `propagations` chain.
- **topology / alerts**: no sampling needed — build directly from `ground_truth.yaml` / `alerts/` as
  described in §1's table.

Put the sampling thresholds (window, caps) in a converter config block, not hardcoded, so they can be
retuned once `context/builder.py` (Phase P1) exists and has real opinions about token budgets.

## 3. The two mapping tables the converter needs (write these as reviewable, editable YAML — not
   buried in Python)

**a) `recommended_actions` text → `action_type`** (config/action_envelope.yaml's 7 allow-listed
types). Example seed entries — extend as more scenarios are converted and new phrasings show up:

```yaml
# config/itbench_action_mapping.yaml (new file, this task creates it)
text_patterns:
  "restart the (pod|container)": restart_pod
  "roll ?back": rollback_deployment
  "scale (up|out|the) (deployment|replicas)": scale_deployment
  "set up autoscaler": scale_deployment       # nearest available match, not exact — mark needs_review
  "clear.*cache": clear_cache
  "increase.*(limit|resource)": increase_resource_limits
  "cordon.*node": cordon_node
  "restart.*service": restart_service
# anything that matches nothing above -> label stays "correct" per ITBench but action_type is left
# null and the whole entry is flagged needs_review with the raw recommended_actions text preserved,
# so a human decides whether it's genuinely out_of_envelope or the mapping table just needs a new rule.
```

**b) Synthesized `destructive` / `ineffective` / `out_of_envelope` candidates**, generated per
scenario from its topology (not hand-written per incident, the way the P0 fixtures were):

- `destructive`: `scale_deployment` with `replicas: 0` targeted at a *different, healthy* group from
  `groups[]` that has an edge to the root-cause entity in `propagations` (mirrors the pattern already
  used in all 6 P0 fixtures — this is deliberately reused so `EnvelopeVerifier`'s structural catch
  still applies to some fraction of these).
- `ineffective`: `restart_pod` or `clear_cache` (pick by root-cause entity `kind`) targeted at the
  *actual* root-cause entity — valid and safe, but per blueprint §6.1 doesn't address a
  non-crashloop/non-cache-shaped fault, so it's a defensible "wrong-but-safe" example.
- `out_of_envelope`: reuse the fixed canary `delete_namespace` against the scenario's `namespace`
  (every P0 fixture already does this) — cheap, consistent, always correct by construction since
  `delete_namespace` is never in `config/action_envelope.yaml`.

## 4. CLI

```
python scripts/convert_itbench.py \
    --source-dir <local ITBench-Lite checkout>/snapshots/sre/v0.2-<uuid> \
    --out-dir fixtures/incidents \
    --mapping config/itbench_action_mapping.yaml \
    [--scenario Scenario-1]        # convert one, for iterating on the mapping table
    [--dry-run]                    # print what would be written, write nothing
```

`--source-dir` is a **local pre-downloaded copy**, not something the script fetches itself — 35
scenarios × ~450 MB of raw telemetry is real bandwidth, and forcing that inside the converter makes it
impossible to iterate on the mapping tables without re-downloading. Document the fetch as a separate,
one-time step:

```bash
huggingface-cli download ibm-research/ITBench-Lite --repo-type dataset \
    --include "snapshots/sre/*" --local-dir <local checkout>
```

## 5. Acceptance criteria

- `python scripts/convert_itbench.py --source-dir <...> --scenario Scenario-1 --dry-run` prints a
  fixture matching the existing JSON shape, with every `labeled_actions[]` entry carrying a
  `provenance` field.
- Running without `--scenario` converts all 35 and writes `fixtures/incidents/itbench-sre-scenario-*.json`.
- Every emitted fixture round-trips through `OfflineEnvAdapter.get_incident()` into a valid
  `IncidentContext` (extend `tests/test_env_offline.py`'s `EXPECTED_FIXTURES` set, or make it
  discover fixtures from disk instead of a hardcoded literal — the hardcoded set only covers the 6 P0
  fixtures today and will silently ignore everything this task adds otherwise).
- No file under `fixtures/incidents/` exceeds a few hundred KB (raw telemetry did not leak through).
- A `THIRD_PARTY_NOTICES.md` (or a "Data sources" section in README.md) carries the Apache-2.0
  attribution and the bibtex citation from §0.
- At least one scenario's `needs_review` entries have been walked through by a human (you) and either
  accepted or corrected, so the P3 acceptance criteria ("labeled dataset built and split by incident")
  has at least one fully-provenanced example to point at, not just auto-generated placeholders.

## 6. What this deliberately does NOT do

- Does not implement `labeling/oracle_labeler.py` or `labeling/review_cli.py` (Phase P3) — those
  modules consume this converter's `needs_review` output; this task only produces it.
- Does not touch FinOps/CISO scenarios.
- Does not attempt live/interactive ITBench cluster mode — that's `env/itbench_adapter.py`'s job
  (parallel, non-blocking track per blueprint §8), unrelated to this offline-snapshot path.

---

## Ready-to-paste Claude Code prompt

```
Read docs/tasks/itbench_converter_spec.md, CLAUDE.md, and ARCHITECTURE_BLUEPRINT.md. Implement
scripts/convert_itbench.py and config/itbench_action_mapping.yaml per the spec. I have a local
checkout of ibm-research/ITBench-Lite's snapshots/sre/ tree at <path> -- use it as --source-dir.
Start with --scenario Scenario-1 --dry-run, show me the output, and don't convert the rest until I
confirm the mapping table and fault_family derivation look right on that one. Meet the spec's §5
acceptance criteria. Do not check any raw ITBench files into git -- only compacted fixture JSON.
```
