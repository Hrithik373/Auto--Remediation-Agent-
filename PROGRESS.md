# Build status

Tracks which phase of [ARCHITECTURE_BLUEPRINT.md](ARCHITECTURE_BLUEPRINT.md) is implemented vs. scaffolded.
Update this file whenever a phase's acceptance criteria are met.

| Phase | Status | Notes |
|-------|--------|-------|
| P0 — Scaffold + schemas + offline env | ✅ Implemented | Schemas, `OfflineEnvAdapter`, deterministic `EnvelopeVerifier`, 6 fixtures, `make offline`, `make test` green. |
| P1 — Diagnosis agent + executor (dry-run) | ✅ Implemented | ReAct agent (4 telemetry tools, strict `propose.py` parsing, feedback loop), seeded `SimulatedDiagnosisAgent` for offline runs, context builder (budget/redaction/signal ablation), executor that enforces the golden rules in code, `/chat` + `/usage` with token/cost ledger + disk cache. `make agent`: 41/41 structured proposals, dry-run only, real apply refused. |
| P2 — Verifier v1 (LLM-judge) + orchestrator | 🔲 Stubbed only | `verifier/llm_judge.py`, `verifier/policy.py`, `orchestrator/loop.py` are interfaces only. |
| P3 — Verifier v2 (learned) + labeling | 🔲 Stubbed only | `verifier/learned.py`, `verifier/features.py`, `labeling/` are interfaces only. |
| P4 — Eval harness + Pareto + ablations | 🔲 Stubbed only | `eval/` contains interfaces only. |
| P5 — Gateway + observability + demo | 🟡 P5a+P5b done, mock-backed | See below. `gateway/api.py`, `observability/`, P5c-e are stubs. |

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
- **P5c (real SSE from a live gateway): not started.** `mock/handlers.ts` *simulates* SSE streaming
  (replays a canned run's steps with real delays) so the demo feels alive today; this is explicitly a
  demo trick, not the real orchestrator. `gateway/api.py` exists as a typed stub matching
  FRONTEND_BLUEPRINT.md §5.1 exactly — Phase P2's orchestrator has to exist before this can be real.
- **P5d (real experiments data): not started.** `mock/fixtures.ts`'s Pareto/prevention/metrics numbers
  are illustrative, not measured — Phase P4 has to run for real before Results shows real numbers.
- **P5e (polish, Grafana embed, `make demo` bringing up the full stack): not started.**

## Verify P0 yourself

```bash
make setup
make test      # pytest: schemas + envelope tests
make offline   # loads fixtures/incidents/pod-crashloop.json and prints its IncidentContext
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

## Next step

1. Human-review at least one converted ITBench scenario (see "Open acceptance item" above).
2. Start a fresh session and run Claude Code prompt #2 from
   [ARCHITECTURE_BLUEPRINT.md §10](ARCHITECTURE_BLUEPRINT.md#10-suggested-first-claude-code-prompts) to build P1.
3. Once P2's orchestrator exists, run FRONTEND_BLUEPRINT.md's P5c prompt (§12) to wire the console to
   a real gateway instead of MSW mocks.
