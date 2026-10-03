# Frontend Architecture Blueprint — SRE Triage Console

> Build spec for Claude Code. Companion to `ARCHITECTURE_BLUEPRINT.md`. Codename: **`sentinel-console`**.
> This is the Phase **P5** deliverable and the surface for the Review 2 "working implementation demoed
> live" and Final "end-to-end demo" checklist items.
>
> **The frontend's single job:** make the safety-gated remediation loop *legible and demoable* — show a
> panel, in real time, the agent diagnosing an incident, proposing an action, the verifier gating it,
> and which layer (envelope / LLM-judge / learned) caught a destructive action and why. Everything else
> is secondary.

---

## 0. Scope and non-goals

**In scope:** incident queue, a triage/detail view with live loop streaming, a verdict panel that exposes
the layered decision, and a results view (Pareto + metrics + ablations) read from DuckDB. Dev/mock mode so
the UI builds before backend endpoints exist.

**Out of scope:** auth/multi-user, editing incidents, a general-purpose observability replacement (embed
Grafana, don't rebuild it), mobile layouts. This is a demo-grade single-operator console, not a product.

---

## 1. What each screen must prove (tie to reviews)

| Screen | What it demonstrates to the panel |
|--------|-----------------------------------|
| Incident Queue | Real incidents from a benchmark, not toy data |
| Triage / Loop | The core module working live — diagnose→propose→verify→act |
| Verdict Panel | **The contribution**: layered gating + *which layer caught what, and why* |
| Results / Experiments | The risk–autonomy Pareto + the envelope-vs-judge "bad-action-prevented" partition |
| Observability | System is instrumented and reproducible |

If a screen doesn't map to a row above, cut it.

---

## 2. Tech stack (pinned)

- **Framework:** React 18 + **Vite** + **TypeScript** (strict).
- **Server state:** TanStack Query (`@tanstack/react-query`) for all fetches + cache.
- **Live loop:** **Server-Sent Events** (native `EventSource`) — one-directional step streaming, simpler
  than WebSocket and sufficient. One SSE stream per run.
- **UI state:** Zustand for the little cross-component UI state (selected incident, τ slider); local
  `useState` for the rest. No Redux.
- **Charts:** **Recharts** (Pareto, metrics bars, risk-coverage). You know it already.
- **Topology graph:** **React Flow** (`reactflow`) for the service dependency graph — nodes = services,
  edges = deps, color = anomaly.
- **Styling:** **Tailwind CSS** + a small set of primitives (Card, Tag, StatusDot). No component library
  bloat; shadcn/ui optional if you want prebuilt Dialog/Tabs.
- **Types shared with backend:** generate TS types from the Pydantic schemas (see §5.3) so `Verdict`,
  `ProposedAction`, `StepRecord`, `RunRecord` never drift between Python and TS.
- **Build/serve:** Vite dev server proxies `/api` → FastAPI gateway. Dockerfile serves the static build
  behind the gateway for `make demo`.

---

## 3. Directory layout (`frontend/`)

```
frontend/
├── index.html
├── vite.config.ts                  # /api proxy → gateway :8000
├── tailwind.config.ts
├── package.json
├── src/
│   ├── main.tsx
│   ├── App.tsx                      # router + layout shell
│   │
│   ├── api/
│   │   ├── client.ts                # fetch wrapper, base URL, error handling
│   │   ├── incidents.ts             # useIncidents, useIncident
│   │   ├── runs.ts                  # useStartRun, useRunStream (SSE), useRun, useRuns
│   │   ├── experiments.ts           # usePareto, useMetrics, useAblations
│   │   └── types.ts                 # ★ generated from Pydantic (§5.3) — do not hand-edit
│   │
│   ├── mock/
│   │   ├── server.ts                # MSW handlers — full UI works with zero backend
│   │   └── fixtures.ts              # canned incidents/runs/pareto for dev + storybook
│   │
│   ├── store/
│   │   └── ui.ts                    # Zustand: selectedIncidentId, tau, verifierChoice
│   │
│   ├── routes/
│   │   ├── QueueRoute.tsx           # /            → incident queue
│   │   ├── TriageRoute.tsx          # /incidents/:id → the hero screen
│   │   ├── ResultsRoute.tsx         # /results     → Pareto + metrics + ablations
│   │   └── ObservabilityRoute.tsx   # /observability → embedded Grafana
│   │
│   ├── features/
│   │   ├── queue/
│   │   │   └── IncidentTable.tsx
│   │   ├── triage/
│   │   │   ├── TelemetryPanel.tsx    # logs / metrics / traces tabs
│   │   │   ├── TopologyGraph.tsx     # React Flow dep graph
│   │   │   ├── DiagnosisCard.tsx     # agent's root-cause statement
│   │   │   ├── ActionCard.tsx        # a ProposedAction rendered
│   │   │   ├── VerdictCard.tsx       # ★ layered decision (the money component)
│   │   │   ├── LoopTimeline.tsx      # ★ step-by-step trace, streams live
│   │   │   └── RunControls.tsx       # start run, pick verifier, τ slider, HITL approve
│   │   ├── results/
│   │   │   ├── ParetoChart.tsx       # ★ risk–autonomy curve, τ marker
│   │   │   ├── MetricsGrid.tsx       # resolution / bad-prevented / false-block / MTTM / cost
│   │   │   ├── PreventionPartition.tsx  # ★ caught-by-envelope vs caught-by-judge stacked bar
│   │   │   └── AblationTable.tsx
│   │   └── shared/
│   │       ├── Card.tsx  Tag.tsx  StatusDot.tsx  KeyValue.tsx  CodeBlock.tsx
│   │
│   ├── lib/
│   │   ├── format.ts                # duration, tokens, usd, risk% formatting
│   │   └── decisionColors.ts        # allow/block/revise/escalate → color tokens
│   │
│   └── styles/index.css
└── Dockerfile
```

Components marked ★ are the ones a panel actually looks at. Build those to a higher polish bar.

---

## 4. Information architecture / user flow

```
QUEUE  ──select──▶  TRIAGE (incident detail)
                      │
                      ├─ TelemetryPanel + TopologyGraph   (the evidence)
                      ├─ RunControls → START RUN
                      │       │
                      │   SSE stream of steps
                      │       ▼
                      ├─ LoopTimeline (steps append live)
                      │       └─ each step: ActionCard + VerdictCard + outcome
                      └─ on finish: run summary (resolved? safe? MTTM? cost?)

RESULTS  ──▶  ParetoChart + MetricsGrid + PreventionPartition + AblationTable
             (reads finished RunRecords from DuckDB via /api/experiments/*)
```

The demo lives entirely in TRIAGE. RESULTS is where the aggregate numbers live for the report/Final.

---

## 5. API contract (this also tells Claude Code what to add to the gateway)

The frontend needs a small read/control API. Add it as `src/sentinel/gateway/api.py` (a FastAPI router
mounted at `/api`). All payloads reuse the existing Pydantic schemas — no new shapes.

### 5.1 Endpoints

```
GET  /api/incidents
       → [{ incident_id, source, fault_family, n_alerts, status }]

GET  /api/incidents/{id}
       → IncidentContext            # telemetry + topology (schemas/incident.py)

GET  /api/config
       → { models, verifier_choice, tau, auto_execute, max_steps }

POST /api/runs
       body: { incident_id, verifier: "envelope"|"llm_judge"|"learned"|"combined",
               tau: float, dry_run: bool }
       → { run_id }

GET  /api/runs/{run_id}/stream         # SSE — the live loop
       event: "step"   data: StepRecord      # one per orchestrator step
       event: "final"  data: RunRecord       # closes the stream

GET  /api/runs                          → [RunRecord summaries]
GET  /api/runs/{run_id}                 → RunRecord (full)

POST /api/runs/{run_id}/decision        # optional HITL override on a blocked/escalated step
       body: { step_idx, human_decision: "approve"|"reject" }
       → StepRecord (updated)

GET  /api/experiments/pareto?verifier=…  → [{ tau, bad_action_prevented, false_block, resolution }]
GET  /api/experiments/metrics            → [{ baseline, resolution, bad_prevented, false_block, mttm_ms, cost_usd }]
GET  /api/experiments/prevention_partition
       → [{ baseline, caught_by_envelope, caught_by_judge_only, missed }]   # ★ the thesis figure
GET  /api/experiments/ablations          → [{ name, variant, metric, value }]
```

### 5.2 The SSE stream is the demo

`POST /api/runs` kicks the orchestrator loop (§5 backend) and `/stream` emits each `StepRecord` **as the
loop produces it** — proposed action, then verdict, then execution result. The `LoopTimeline` appends each
event. This is what makes the demo feel alive instead of a table that appears fully-formed. Backend: run the
loop in a background task, push steps onto an `asyncio.Queue`, drain it into the SSE response.

### 5.3 Shared types (no drift)

Generate `src/api/types.ts` from the Pydantic models rather than hand-writing them:
`datamodel-code-generator` or `pydantic2ts` → run it in `make types`. `Verdict.decision`,
`ProposedAction`, `StepRecord`, `RunRecord` come straight from `schemas/`. If a schema changes, regenerate.

---

## 6. The three components that matter

### 6.1 `VerdictCard` — makes the contribution visible

Renders a `Verdict` as a **decision pipeline**, not a single verdict. The panel must be able to *see* that
the envelope passed something and the judge caught it.

```
┌─ VERDICT ─────────────────────────────── decision: BLOCK ─┐
│  Envelope   ✔ passed   (structurally valid: replicas ≥ 1) │
│  LLM-judge  ✘ BLOCK    risk 0.87                           │
│             └ "cordon_node on node-7 drains 4 healthy      │
│                pods of an unrelated service; not required  │
│                to fix the checkout crashloop."             │
│  Learned    ✘ 0.91     (above τ = 0.50)                    │
│  ─────────────────────────────────────────────────────    │
│  COMBINED   BLOCK  ·  never reached executor               │
└───────────────────────────────────────────────────────────┘
```

Props: `verdict: Verdict`, `tau: number`, `envelopeReason?: string`. Color the final decision band by
`decisionColors[verdict.decision]`. When a layer is inactive for the current run config, gray it out — the
viewer should see *which layers were in play*.

### 6.2 `LoopTimeline` — the live trace

Vertical timeline; each node is one orchestrator step. Streams in via SSE. Each step shows: step index,
`ActionCard` (collapsed), `VerdictCard` (collapsed → expand on click), and an outcome pill
(`applied · resolved`, `blocked`, `revised → retry`, `escalated`). The final node shows the run summary:
resolved yes/no, **unsafe-action-reached-exec yes/no** (the safety headline), MTTM, tokens, cost.

State machine per step, drive the pill + color:
`proposed → verifying → (allowed→executing→resolved|failed) | blocked | revise`.

### 6.3 `ParetoChart` + `PreventionPartition` — the results thesis

`ParetoChart`: Recharts scatter/line of **bad-action-prevented (y) vs false-block (x)** across τ, one series
per verifier variant, with a draggable τ marker synced to the Zustand `tau`. Moving τ live is a great viva
moment ("here's the trade-off knob").

`PreventionPartition`: stacked bar per baseline — `caught_by_envelope` / `caught_by_judge_only` / `missed`.
**This is the single most important figure in the project**, because it proves each layer earns its place:
the envelope alone leaves a residue of destructive actions (e.g. `cordon_node`) that only the judge/learned
layer catches. Your P0 finding — envelope catches scale-to-zero but not cordon — is exactly this bar, made
empirical.

---

## 7. State & data flow

- All server data via TanStack Query hooks in `api/`. Query keys: `["incidents"]`, `["incident", id]`,
  `["runs"]`, `["run", id]`, `["pareto", verifier]`, etc.
- The live run is **not** a Query — it's an `EventSource` opened by `useRunStream(runId)`, accumulating
  steps into local state and invalidating `["runs"]` on `final`.
- Zustand `ui` store holds only: `selectedIncidentId`, `tau`, `verifierChoice`, `dryRun`. These drive both
  `RunControls` and `ParetoChart`'s τ marker so the two views stay consistent.
- No `localStorage` (not needed; also avoids the artifact-storage footgun if any of this is ever pasted
  into a Claude artifact for a quick preview).

---

## 8. Design direction (SRE console aesthetic)

Dense, dark, information-first — it should read like a real on-call tool, not a marketing dashboard. That
realism helps in the viva.

- **Theme:** dark slate background, one accent (electric cyan) for interactive elements. Restraint.
- **Decision color tokens** (`lib/decisionColors.ts`): allow → emerald, block → red, revise → amber,
  escalate → violet. Use them consistently on pills, verdict bands, and timeline nodes so color *means*
  decision everywhere.
- **Typography:** UI sans (Inter) for chrome; **monospace (JetBrains Mono)** for logs, action types,
  params, IDs, risk scores. Anything a machine emitted is mono.
- **Tags:** fault-family and action-type render as small mono tags. Severity as a colored `StatusDot`.
- **Density:** tables tight, generous only around the VerdictCard and the final run summary (the two things
  people read closely).
- **Motion:** minimal — a subtle pulse on the step currently `verifying`, and new timeline nodes fade in as
  they stream. No decorative animation.

---

## 9. Demo script (rehearse this — it *is* your Review 2/Final live demo)

Bake this exact path in and make sure it's reliable. ~3 minutes.

1. **Queue** → point out incidents are real benchmark snapshots (fault-family tags visible).
2. Open a **crashloop** incident. Show TelemetryPanel (the error logs) + TopologyGraph (the failing
   service lit red). "Here's what the on-call engineer would see."
3. `RunControls`: verifier = **combined**, τ = 0.5. **Start run.**
4. Watch `LoopTimeline` stream: agent diagnoses → proposes the *correct* fix (`restart_deployment`) →
   VerdictCard shows envelope ✔ / judge ✔ → applied → **resolved**. "Happy path: it fixes it."
5. Open the **bad-rollout** incident. Start run. This time the agent proposes **`cordon_node`** (destructive).
   VerdictCard: **envelope ✔ passed** (structurally valid) → **judge ✘ BLOCK** with the reason →
   COMBINED BLOCK → outcome pill "blocked · never reached executor". **This is the whole thesis in one screen.**
6. Flip to **Results**. Show `PreventionPartition`: envelope-only leaves a red "missed" slice; +judge shrinks
   it. Show `ParetoChart`; drag τ to show the safety/autonomy trade-off moving. "This knob is the contribution."

Have a recorded fallback of this exact run in case live inference is slow on demo day.

---

## 10. Build sub-phases (within P5) + acceptance

**P5a — shell + mock mode.** Router, layout, Tailwind, MSW mock server + fixtures, generated `types.ts`,
all `api/` hooks pointing at MSW. *Accept:* every screen renders end-to-end from mocks with zero backend;
`npm run dev` works offline.

**P5b — queue + triage (static).** IncidentTable, TelemetryPanel, TopologyGraph, DiagnosisCard, ActionCard,
VerdictCard rendering a *canned* run. *Accept:* a full run displays correctly from a fixture RunRecord,
including the layered VerdictCard.

**P5c — live loop.** Wire `useRunStream` to real SSE from the gateway `/api/runs/{id}/stream`; LoopTimeline
appends live; RunControls start/verifier/τ/dry-run wired. *Accept:* clicking Start on a real incident streams
steps live and ends with a run summary; the demo-script steps 3–5 work against the real backend.

**P5d — results.** ParetoChart, MetricsGrid, PreventionPartition, AblationTable from `/api/experiments/*`.
*Accept:* Pareto + partition render from real DuckDB-backed endpoints; τ marker syncs with the store.

**P5e — polish + demo.** Design pass, motion, Grafana embed, Dockerfile, `make demo` brings up console +
gateway + Grafana together. *Accept:* `make demo` → the full §9 script runs clean.

---

## 11. `CLAUDE.md` addendum (append to the repo-root file)

```markdown
## Frontend conventions (sentinel-console)
- Types in src/api/types.ts are GENERATED from Pydantic (make types). Never hand-edit them.
  If the UI needs a field, add it to the Pydantic schema first, then regenerate.
- The frontend must build and run fully against MSW mocks with the backend down (mock mode).
  Never let a component hard-require a live endpoint to render.
- Color means decision everywhere: use lib/decisionColors.ts. Never hardcode allow/block colors.
- Anything a machine emitted (logs, params, action_type, IDs, risk scores) renders in monospace.
- The live run is an EventSource, NOT a TanStack Query. Do not poll for step updates.
- No localStorage/sessionStorage. UI state lives in Zustand; server state in TanStack Query.
- VerdictCard must always show ALL layers (graying out inactive ones), never just the final decision —
  the layered view is the project's contribution and must stay visible.
```

---

## 12. Suggested Claude Code prompts (one sub-phase per session)

1. *"Read FRONTEND_BLUEPRINT.md. Build P5a: Vite+React+TS+Tailwind scaffold matching §3, the MSW mock
   server with fixtures for 6 incidents and 2 canned runs, generate src/api/types.ts from the Pydantic
   schemas, and all api/ hooks pointing at MSW. Every route must render from mocks with no backend. Meet
   P5a acceptance."*
2. *"P5b: implement IncidentTable, TelemetryPanel, TopologyGraph (React Flow), DiagnosisCard, ActionCard,
   and VerdictCard per §6.1. Render the canned run fixture end-to-end including the layered VerdictCard.
   Meet P5b acceptance."*
3. *"P5c: add the SSE run endpoint to the gateway (src/sentinel/gateway/api.py) and wire useRunStream +
   LoopTimeline + RunControls so a real incident streams steps live. Meet P5c acceptance and demo §9 steps 3–5."*
4. …P5d, P5e likewise.

---

## 13. Where this leaves you at each review

- **Review 2:** P5a–P5c give a *live-demoable core module* — the loop streaming on screen, the VerdictCard
  showing a destructive action being caught. That single screen satisfies "working implementation demoed
  live (not just screenshots)."
- **Final:** P5d–P5e give the Pareto + prevention-partition figures rendered from real runs, plus a
  rehearsed, reproducible demo path — the "defend every design choice" bar, because the UI literally shows
  *why* each verifier layer exists.
