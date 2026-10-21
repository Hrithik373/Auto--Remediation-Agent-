# Build status

Tracks which phase of [ARCHITECTURE_BLUEPRINT.md](ARCHITECTURE_BLUEPRINT.md) is implemented vs. scaffolded.
Update this file whenever a phase's acceptance criteria are met.

| Phase | Status | Notes |
|-------|--------|-------|
| P0 — Scaffold + schemas + offline env | ✅ Implemented | Schemas, `OfflineEnvAdapter`, deterministic `EnvelopeVerifier`, 6 fixtures, `make offline`, `make test` green. |
| P1 — Diagnosis agent + executor (dry-run) | ✅ Implemented | ReAct agent (4 telemetry tools, strict `propose.py` parsing, feedback loop), seeded `SimulatedDiagnosisAgent` for offline runs, context builder (budget/redaction/signal ablation), executor that enforces the golden rules in code, `/chat` + `/usage` with token/cost ledger + disk cache. `make agent`: 41/41 structured proposals, dry-run only, real apply refused. |
| P2 — Verifier v1 (LLM-judge) + orchestrator | ✅ Implemented | Fail-closed LLM judge (own prompt + ledger), `CombinedPolicy` (envelope AND risk < τ, all 3 layers always reported), 5 variants (`none`/`envelope`/`llm_judge`/`learned`/`combined`), orchestrator loop with post-verdict eval labels, DuckDB store. `make run`: envelope blocks all 5 scale-to-zero + 3 out-of-envelope and allows all 33 correct actions, but 7 destructive `cordon_node` actions pass it — the residue P3 must close. The judge runs only with Anthropic credentials (tested with a scripted LLM). |
| P3 — Verifier v2 (learned) + labeling | ✅ Implemented | Provenance-typed labels, oracle labeler, rule-based hard cases (`config/labeling_rules.yaml`), review CLI (`make review`), telemetry-only features, XGBoost + Platt calibration **cross-fitted by incident** (every incident scored by a model that never saw it). `make train`: out-of-fold AUC 0.998 / ECE 0.023. **Read with the type-only baseline (AUC 0.987)**: labels are largely rule-determined; on the within-type subset (same action type, both labels) the learned verifier gets AUC 0.995 vs 0.970. End to end (`make run VARIANT=learned`): destructive actions allowed drop from 9 (envelope only) to 1. |
| P4 — Eval harness + Pareto + ablations | ✅ Implemented (offline) | `make eval` (~5 min) retrains, runs 7,585 seeded runs (41 incidents × 5 seeds × 37 cells) into DuckDB, and rebuilds `runs/eval/results.{md,json}` + 4 figures from the store; `notebooks/analysis.ipynb` reads the same code. Bootstrap CIs resample incidents. Headline (τ=0.5): runs executing a destructive action — ungated 33%, envelope 21%, envelope+learned **1%**; with block→retry, envelope+learned resolves 93% with net-safe resolution **92% vs 67%** ungated. LLM baselines (judge, ReAct, combined) and the telemetry/model-size sweeps are listed as *not run* unless `make eval WITH_LLM=1`. |
| P5 — Gateway + observability + demo | ✅ Implemented (Docker images unbuilt here) | Real console API with live SSE, experiments served from DuckDB, Prometheus `/metrics`, provisioned Grafana dashboard, Dockerfiles + `docker compose` stack. `make e2e` rehearses the §9 demo in headless Chromium against the real gateway: **passes, zero console errors**. See below. |
| P6 — Assistant (explainer chatbot) | ✅ Implemented | [ASSISTANT_BLUEPRINT.md](ASSISTANT_BLUEPRINT.md). `src/sentinel/assistant/` + `/api/assistant/*` + the console's **Assistant** route. Explains the system (docs + module docstrings, with citations) and **why** a verdict was allow/revise/block: deciding layer, risk vs τ, threshold and variant counterfactuals, benchmark label in the eval's own terms. Judgements come only from the real `CombinedPolicy` (verify only); no assistant module references the executor (AST-tested) and `apply_action` is never called (runtime-tested). LLM mode (own prompt, client and ledger; Groq by default) with a tool loop; deterministic offline mode when there is no key or the LLM fails. Triage steps get **Ask why**. 31 tests in `tests/test_assistant.py`; verified live against Groq. |

### P5 detail (FRONTEND_BLUEPRINT.md)

`frontend/` (`sentinel-console`) is a real, building, passing app — not a scaffold:
- **P5a (shell + mock mode): done.** Vite+React+TS(strict)+Tailwind, TanStack Query, Zustand, MSW.
  `frontend/src/api/types.ts` is genuinely generated from the Pydantic schemas (`make types` runs
  `scripts/export_schemas.py` → `frontend/scripts/gen-types.mjs`, both real, both executed — not
  hand-authored). Extending `Verdict` with `LayerVerdict`/`layers` (schemas/verdict.py) was done in
  this phase so `VerdictCard` has a real field to render, not an invented shadow type.
- **P5b (queue + triage, static/canned): done.** All routes render; `mock/fixtures.ts` mirrors the
  real P0 backend fixtures 1:1 (same 6 incident_ids, same telemetry for pod-crashloop and
  bad-rollout-latency) so the console isn't disconnected from the eval harness it'll eventually front.
  Verified with a real headless-browser pass (Playwright): Queue → Triage → Start run → streamed
  LoopTimeline with layered VerdictCard → run summary → Results (Pareto + prevention partition +
  metrics + ablations), zero console errors. `npm run build`, `tsc -b`, and `eslint` all pass clean.
  Chart colors were run through the dataviz skill's `validate_palette.js` against the console's actual
  dark surface, not eyeballed.
- **P5c (live loop): done.** `POST /api/runs` starts the real orchestrator in a background thread;
  `/api/runs/{id}/stream` emits each `StepRecord` as the loop produces it, then the `RunRecord`
  (reconnects replay the whole log). Display pacing (`gateway.step_delay_ms`) only spaces events — the
  run is already decided. `dry_run=false` is refused (403) unless the gateway config sets
  `auto_execute`; HITL decisions are recorded for audit and never execute anything.
- **P5d (results): done.** `/api/experiments/*` rebuild the tables from `make eval`'s DuckDB rows via
  `eval/report.py` (the same code as the report). Mock mode now shows a **measured** snapshot
  (`make mock-results` → `frontend/src/mock/experiments.json`), not illustrative numbers. The partition
  field is `caught_by_secondary_only` (offline it is the learned layer, so "judge only" was wrong).
- **P5e (demo): done, Docker path unverified on this machine.** `make demo` = `docker compose up
  --build` (console :4173 via nginx with SSE-safe proxying, gateway :8080, Prometheus :9090, Grafana
  :3000 with the provisioned "sentinel — live loop" dashboard). `docker compose config` validates, but
  the Docker engine wasn't running here, so the images have not been built. `make demo-local` runs the
  same demo without Docker (gateway + `npm run dev:live`) and is what `make e2e` verifies.
- Fixed along the way: the header always claimed "mock mode"; `ParetoChart` colored series by index
  (now by variant); ablation rows had duplicate React keys and rendered step counts as percentages;
  the partition drew "missed" in green (now magenta, first against the baseline, re-validated).

## Verify it yourself

```bash
make setup     # pip install -e ".[dev]"
make test      # ~620 tests, ~15 s
make offline   # P0: load a fixture, run the envelope gate
make agent     # P1: a structured proposal + dry-run result for all 41 incidents
make run       # P2: end-to-end runs into DuckDB (VARIANT=none|envelope|learned|...)
make train     # P3: cross-fitted learned verifier, out-of-fold AUC/ECE vs a type-only baseline
make eval      # P4: everything from scratch -> runs/eval/{results.md,results.json,figures/}  (~5 min)
make e2e       # P5: headless-browser rehearsal of the live demo against the real gateway
```

## Dataset trajectory — ✅ ITBench converter implemented

`fixtures/incidents/` now holds **41 incidents**: the 6 hand-built P0 ones plus 35 converted from the
public `ibm-research/ITBench-Lite` SRE scenarios (Apache-2.0, see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)) by `scripts/convert_itbench.py`
(`make fetch-itbench` → ~14 GB into gitignored `data/`; `make convert-itbench`).

- 179 labeled actions on the ITBench set: 43 `correct` (all `itbench_derived`), 66 `destructive`,
  35 `ineffective`, 35 `out_of_envelope` (all `converter_synthesized`). Every entry is `needs_review`.
- 34/35 scenarios are resolvable within the envelope; Scenario-38 (investigation-only remedies) is a
  "should escalate" case. Getting there required extending `config/action_envelope.yaml` with
  `toggle_feature_flag`, `remove_fault_injection` (kind-enum gated) and `increase_namespace_quota` —
  see the deviations list at the top of [the spec](docs/tasks/itbench_converter_spec.md).
- **Open acceptance item (needs a human):** spec §5 asks that at least one scenario's `needs_review`
  entries be walked through by a human and marked `human_reviewed`. That's `labeling/review_cli.py`
  (Phase P3) or a manual edit — the converter deliberately never sets it. Known weak spots to review
  first: Scenario-12's `increase_resource_limits` target (`frontend`; likely `recommendation`) and
  Scenario-1's low-confidence "set up autoscaler" → `scale_deployment frontend-proxy`.

## Verify the frontend yourself

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, mock mode by default (VITE_USE_MOCKS != "false")
npm run typecheck  # tsc -b --noEmit
npm run lint        # eslint . --max-warnings 0
npm run build       # tsc -b && vite build
```
`make types` (repo root) regenerates `frontend/src/api/types.ts` from the Pydantic schemas after any
schema change — never hand-edit that file.

## What is left (needs a human, money, or a running Docker engine)

1. **Human label review** (open acceptance item above): `make review FIXTURE=fixtures/incidents/<id>.json`.
2. **LLM baselines**: `make eval WITH_LLM=1` runs the LLM judge, combined and ReAct baselines plus the
   telemetry/model-size sweeps. This spends Anthropic API money; LLM calls are disk-cached under
   `runs/llm_cache`, so reruns are free.
3. **Docker demo**: start Docker Desktop, then `make demo`; `make demo-local` works without Docker.
4. **Cluster adapters** (blueprint §8, parallel/non-blocking): `env/aiopslab_adapter.py` and
   `env/itbench_adapter.py` are still stubs; everything runs on the offline adapter.
