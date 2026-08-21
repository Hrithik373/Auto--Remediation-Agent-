# Safety-Gated LLM Auto-Remediation Agent — Architecture Blueprint

> Build spec for Claude Code. Project codename: **`sentinel-remediate`**.
> Contribution being built: a **pre-execution verification layer** that gates an LLM remediation
> agent's proposed actions on an AIOps benchmark, producing a measured **safety ↔ autonomy** trade-off.
> Novelty sits in the intersection: pre-execution verification applied to *operationally-correct*
> AIOps remediation (not adversarial/prompt-injection safety), evaluated on AIOpsLab / ITBench.

---

## 0. How to read this document

This is written to be consumed by an agentic CLI (Claude Code). Build **phase by phase**, in order.
Each phase has explicit **acceptance criteria** — do not advance until they pass. Phases map to the
M.Tech review milestones so your repo state always matches what a panel expects to see.

| Phase | Deliverable | Maps to |
|-------|-------------|---------|
| P0 | Repo scaffold, schemas, env adapter (offline mode) | Review 0/1 |
| P1 | Diagnosis agent + action schema + executor (dry-run) | Review 1 |
| P2 | Verifier v1 (LLM-judge) + orchestrator loop | Review 2 core module |
| P3 | Verifier v2 (learned/XGBoost) + labeling pipeline | Review 2 |
| P4 | Evaluation harness + risk–autonomy Pareto + ablations | Review 2 → Final |
| P5 | FastAPI gateway, observability, triage console demo | Final live demo |

---

## 1. System overview

```
                    ┌─────────────────────────────────────────────────────┐
                    │                  ORCHESTRATOR                        │
                    │   diagnose → propose → VERIFY → act/revise/escalate  │
                    └─────────────────────────────────────────────────────┘
                          │            │            │            │
              ┌───────────▼──┐  ┌──────▼─────┐ ┌────▼──────┐ ┌───▼─────────┐
              │  ENV ADAPTER │  │ DIAGNOSIS  │ │ VERIFIER  │ │  EXECUTOR   │
              │ AIOpsLab /   │  │  AGENT     │ │ (the      │ │ dry-run |   │
              │ ITBench |    │  │ (ReAct)    │ │ contrib.) │ │ apply +     │
              │ offline snap │  │            │ │           │ │ oracle check│
              └──────┬───────┘  └─────┬──────┘ └─────┬─────┘ └──────┬──────┘
                     │                │              │              │
              telemetry ctx      tool calls     allow/block/    action result
              (logs/metrics/     over env       revise + score   + post-repair
               traces/topo)                     + rationale      verification
                     │                                                  │
              ┌──────▼──────────────────────────────────────────────────▼──┐
              │        LLM GATEWAY (FastAPI proxy) — routing, cost, logs     │
              └──────────────────────────────────────────────────────────────┘
                     │                                                  │
              ┌──────▼───────┐                                  ┌───────▼──────┐
              │ RUN STORE    │                                  │ OBSERVABILITY│
              │ DuckDB/Parquet│─────────────────────────────────▶│ Prom/Grafana │
              └──────┬───────┘                                  └───────┬──────┘
                     │                                                  │
              ┌──────▼──────────────────────────────────────────────────▼──┐
              │            EVAL HARNESS  →  metrics, Pareto, ablations       │
              └──────────────────────────────────────────────────────────────┘
                                          │
                                 ┌────────▼─────────┐
                                 │ TRIAGE CONSOLE   │  (React/Vite — live demo)
                                 └──────────────────┘
```

The **critical design principle** (borrowed from the agent-safety literature): treat the LLM as an
**untrusted planner**. The diagnosis agent only *proposes*; nothing reaches the environment's control
plane until the verifier clears it. Proposal generation is separated from environment-facing execution.

---

## 2. Tech stack (pinned to your existing skills)

- **Language / runtime:** Python 3.11, `pyproject.toml` + `uv` (or `pip` + `requirements.txt`).
- **Schemas / validation:** Pydantic v2 (every cross-module payload is a Pydantic model).
- **Agent loop:** custom lightweight ReAct orchestrator (no heavy framework lock-in). Anthropic SDK
  as primary LLM client; keep a thin `LLMClient` interface so OpenAI/vLLM are drop-in.
- **Learned verifier:** scikit-learn + XGBoost (reuses your TF-IDF + XGBoost intent-classifier pattern).
- **Run storage:** DuckDB over Parquet (reuses your candle-store pattern) — every run is a row, every
  step is a row, fully queryable for the eval harness.
- **Gateway:** FastAPI (reuses your existing proxy) — LLM routing, token/cost accounting, request logs.
- **Observability:** `prometheus-client` + Grafana dashboards (reuses your ITU stack).
- **Benchmark env:** AIOpsLab (Microsoft) and/or ITBench (IBM) on `kind`/`minikube`; **offline
  snapshot mode** as the always-works fallback.
- **Frontend:** React + Vite (reuses your SRE triage console).
- **Infra:** Docker Compose for gateway + Grafana + Prometheus; `kind` for the k8s benchmark.
- **Testing:** pytest + a golden-incident fixture set that runs without any cluster.

---

## 3. Repository layout

```
sentinel-remediate/
├── CLAUDE.md                       # conventions Claude Code must follow (see §9)
├── README.md                       # setup, run, reproduce (Review 2 requires this)
├── pyproject.toml
├── requirements.txt
├── docker-compose.yml              # gateway + prometheus + grafana
├── Makefile                        # make setup | test | eval | demo | offline
│
├── config/
│   ├── default.yaml                # model names, token budgets, thresholds
│   ├── action_envelope.yaml        # allow-listed action types + param schemas
│   └── grafana/                    # provisioned dashboards
│
├── src/sentinel/
│   ├── schemas/                    # Pydantic contracts (§4) — the spine of the system
│   │   ├── incident.py             # IncidentContext, Telemetry
│   │   ├── action.py               # ProposedAction, ActionEnvelope, ExecutionResult
│   │   ├── verdict.py              # Verdict, RiskScore
│   │   └── run.py                  # RunRecord, StepRecord (persistence rows)
│   │
│   ├── env/                        # ENV ADAPTER
│   │   ├── base.py                 # EnvAdapter ABC (get_incident, apply_action, evaluate)
│   │   ├── aiopslab_adapter.py
│   │   ├── itbench_adapter.py
│   │   └── offline_adapter.py      # reads snapshot fixtures — no cluster needed
│   │
│   ├── context/                    # TELEMETRY → LLM CONTEXT
│   │   ├── builder.py              # compaction, token-budgeting, redaction
│   │   └── retrievers.py           # log/metric/trace/topology selectors
│   │
│   ├── agent/                      # DIAGNOSIS AGENT
│   │   ├── react.py                # ReAct loop (baseline + your variant)
│   │   ├── tools.py                # get_logs, get_metrics, get_traces, get_topology
│   │   └── propose.py              # emits a structured ProposedAction
│   │
│   ├── verifier/                   # ★ THE CONTRIBUTION ★
│   │   ├── base.py                 # Verifier ABC → Verdict
│   │   ├── llm_judge.py            # v1: LLM-as-judge verifier
│   │   ├── learned.py              # v2: XGBoost verifier
│   │   ├── features.py             # feature extraction for v2
│   │   ├── envelope.py             # typed allow-list + param validation (deterministic gate)
│   │   └── policy.py               # combine: envelope AND (judge OR learned) → final verdict
│   │
│   ├── executor/                   # EXECUTOR
│   │   ├── executor.py             # dry-run | apply; off-by-default auto-execute
│   │   └── rollback.py             # reversibility helpers where supported
│   │
│   ├── orchestrator/               # THE LOOP
│   │   └── loop.py                 # diagnose→propose→verify→act/revise/escalate
│   │
│   ├── gateway/                    # FASTAPI LLM PROXY
│   │   ├── app.py                  # /chat, /health, cost + token accounting
│   │   └── clients.py              # LLMClient interface (anthropic/openai/vllm)
│   │
│   ├── labeling/                   # GROUND-TRUTH FOR "UNSAFE ACTION"
│   │   ├── schema.py               # label taxonomy (§6)
│   │   ├── oracle_labeler.py       # derive labels from env oracle + rules
│   │   └── review_cli.py           # human-in-the-loop label review tool
│   │
│   ├── eval/                       # EVALUATION HARNESS
│   │   ├── runner.py               # N incidents × seeds → RunRecords
│   │   ├── metrics.py              # resolution, bad-action-prevented, false-block, MTTM, cost
│   │   ├── pareto.py               # risk–autonomy curve
│   │   └── ablations.py            # signal on/off, verifier on/off, threshold sweep
│   │
│   ├── store/
│   │   └── duckdb_store.py         # write/read RunRecord + StepRecord
│   │
│   └── observability/
│       └── metrics.py              # prometheus counters/histograms
│
├── frontend/                       # TRIAGE CONSOLE (React/Vite)
│   └── src/...                     # incident feed, proposed action, verdict, live loop
│
├── fixtures/
│   └── incidents/                  # offline snapshots (logs/metrics/traces/topo/oracle)
│
├── notebooks/
│   └── analysis.ipynb              # figures for the report
│
└── tests/
    ├── test_schemas.py
    ├── test_envelope.py
    ├── test_verifier.py
    ├── test_orchestrator.py
    └── test_eval_metrics.py
```

---

## 4. Core data contracts (build these FIRST — everything depends on them)

Every module talks through these Pydantic models. Freeze them in P0.

```python
# schemas/incident.py
class Telemetry(BaseModel):
    logs: list[str]
    metrics: dict[str, list[float]]        # metric_name -> series
    traces: list[dict]                     # span records
    topology: dict                         # service dependency graph
    alerts: list[dict]

class IncidentContext(BaseModel):
    incident_id: str
    source: Literal["aiopslab", "itbench", "offline"]
    fault_family: str | None               # ground-truth family (for eval only)
    telemetry: Telemetry
    budget_tokens: int                     # context compaction target

# schemas/action.py
class ProposedAction(BaseModel):
    action_type: str                       # must exist in action_envelope.yaml
    target: str                            # service / pod / namespace / resource
    params: dict
    rationale: str                         # agent's justification
    predicted_effect: str                  # what the agent thinks will happen

class ExecutionResult(BaseModel):
    executed: bool
    dry_run: bool
    resolved: bool | None                  # from env oracle (None if not executed)
    side_effects: list[str]
    error: str | None

# schemas/verdict.py
class Verdict(BaseModel):
    decision: Literal["allow", "block", "revise"]
    risk_score: float                      # 0..1
    reasons: list[str]
    verifier: Literal["envelope", "llm_judge", "learned", "combined"]

# schemas/run.py
class StepRecord(BaseModel):
    step_idx: int
    proposed: ProposedAction
    verdict: Verdict
    result: ExecutionResult | None
    tokens: int
    latency_ms: float

class RunRecord(BaseModel):
    incident_id: str
    seed: int
    config_hash: str                       # reproducibility
    steps: list[StepRecord]
    final_resolved: bool
    unsafe_action_reached_exec: bool       # the key safety metric
    mttm_ms: float | None
    total_tokens: int
    total_cost_usd: float
```

---

## 5. Module contracts (interfaces Claude Code implements against)

**EnvAdapter** (`env/base.py`) — the only thing that touches the benchmark:
```python
class EnvAdapter(ABC):
    def list_incidents(self) -> list[str]: ...
    def get_incident(self, incident_id: str) -> IncidentContext: ...
    def apply_action(self, action: ProposedAction, dry_run: bool) -> ExecutionResult: ...
    def evaluate(self, incident_id: str) -> bool: ...        # oracle: is it resolved?
    def ground_truth_action_safe(self, action: ProposedAction, incident_id: str) -> bool | None:
        ...  # label source for the verifier (offline/oracle-derived)
```
Implement `offline_adapter.py` FIRST and fully. AIOpsLab/ITBench adapters implement the same ABC so the
rest of the system is cluster-agnostic. This is the single most important de-risking decision — the whole
pipeline runs and is testable with zero Kubernetes.

**Verifier** (`verifier/base.py`):
```python
class Verifier(ABC):
    def verify(self, incident: IncidentContext, action: ProposedAction) -> Verdict: ...
```
Three concrete verifiers, combined by `policy.py`:
1. `envelope.py` — deterministic. Rejects any action not in the allow-list, or with params failing
   schema/least-privilege checks (e.g. blast-radius caps, no destructive ops on prod namespace). This
   is your hard gate; it never depends on the LLM.
2. `llm_judge.py` — v1. Prompts a model with (compacted incident + proposed action + predicted effect)
   and asks for `{allow|block|revise}` + risk + reasons, structured JSON output.
3. `learned.py` — v2. XGBoost over features from `features.py` (see §6). Outputs a calibrated risk score.

`policy.py` combines: **final = envelope_pass AND (score < threshold τ)**. τ is what you sweep to draw
the Pareto curve. This layering is the experiment.

**Orchestrator loop** (`orchestrator/loop.py`):
```
for step in range(max_steps):
    action = agent.propose(context)
    verdict = verifier.verify(incident, action)
    if verdict.decision == "allow":
        result = executor.run(action, dry_run=config.dry_run)
        if env.evaluate(incident_id): break        # resolved
    elif verdict.decision == "revise":
        context = agent.incorporate_feedback(verdict.reasons)   # closed-loop, TRIAD-style
    else:  # block
        escalate_to_human(); break
record_step(...)
```

---

## 6. The verifier design (this is your novelty — spec it carefully)

### 6.1 Label taxonomy — what "unsafe action" means

The panel *will* attack this. Define it deterministically in `labeling/schema.py`:

- **`correct`** — action matches the oracle-appropriate remediation family for the fault; resolves incident.
- **`ineffective`** — valid action, wrong target/params; does not resolve (not dangerous, just wrong).
- **`destructive`** — action with irreversible/high-blast-radius effect (deletes state, scales to zero a
  healthy dependency, restarts wrong namespace). **This is the class the verifier must catch.**
- **`out_of_envelope`** — action type not in the allow-list.

`oracle_labeler.py` derives these from: (a) the env oracle (resolved / not), (b) a rules table mapping
fault-family → acceptable action-families, (c) blast-radius heuristics on params. `review_cli.py` lets you
spot-check and correct labels — you keep the human-reviewed set as the gold eval set. Document the inter-step
of oracle-derived vs human-reviewed labels in the report; that traceability is what makes the ground truth
defensible.

### 6.2 Features for the learned verifier (`features.py`)

- Action features: action_type (one-hot), target scope (pod/service/namespace), param blast-radius,
  reversibility flag, matches-fault-family (from topology reasoning).
- Context features: incident fault-family signals, #anomalous services, alert severity, topology depth
  of target, TF-IDF over the agent's rationale (reuses your TF-IDF pattern).
- Agent-confidence features: token-logprob confidence if available, self-reported confidence.

Train/val/test split **by incident** (never leak an incident across splits). Report calibration (ECE) so
the risk score is meaningful for thresholding.

---

## 7. Evaluation harness (drives every figure in the report)

`eval/runner.py` runs the grid: `incidents × seeds × config`. `eval/metrics.py` computes:

- **Resolution rate** — fraction of incidents resolved end-to-end.
- **Bad-action-prevented rate** — of all `destructive` actions proposed, fraction blocked before exec.
- **False-block rate** — of all `correct` actions proposed, fraction wrongly blocked.
- **Net safe resolutions** — resolved AND no destructive action ever executed.
- **MTTM** — mean time-to-mitigation (steps / wall-clock).
- **Cost** — tokens and USD per incident (from the gateway's accounting).

`eval/pareto.py` sweeps τ and plots **bad-action-prevented vs false-block** (and vs resolution rate) — the
**risk–autonomy Pareto**. This single figure is the headline result.

`eval/ablations.py` (Review 2 needs these): verifier off vs on; envelope-only vs +judge vs +learned;
telemetry-signal ablation (logs-only vs logs+metrics+topology); τ sweep; model-size sweep.

**Baselines to run** (all through the same harness):
1. Ungated agent (no verifier) — the "diagnosis-recovery gap" reference.
2. ReAct baseline (the standard AIOpsLab agent).
3. Envelope-only (deterministic gate, no LLM/learned verifier).
4. LLM-judge verifier (v1).
5. Learned verifier (v2) — your best system.

---

## 8. Phased build plan with acceptance criteria

**P0 — Scaffold + schemas + offline env.** Repo, `pyproject`, all Pydantic schemas, `offline_adapter.py`,
5–10 hand-built incident fixtures with oracles. `Makefile` targets. `pytest` green on schema + envelope tests.
*Accept:* `make offline` loads an incident and prints its context; tests pass; zero cluster required.

**P1 — Diagnosis agent + executor (dry-run).** ReAct loop with the four telemetry tools, `propose.py`
emitting a valid `ProposedAction`, executor in dry-run only, gateway stub with token accounting.
*Accept:* agent produces a structured action for every fixture; executor logs a dry-run `ExecutionResult`;
no action can reach "apply" yet.

**P2 — Verifier v1 + orchestrator.** `envelope.py` + `llm_judge.py` + `policy.py`; full orchestrator loop
with allow/block/revise; run store writing `RunRecord`s to DuckDB. **This is the Review 2 "core module
demoed live" deliverable.**
*Accept:* end-to-end run on offline fixtures produces RunRecords; a deliberately-destructive fixture action
is blocked; a correct action is allowed; results queryable from DuckDB.

**P3 — Verifier v2 + labeling.** `labeling/` taxonomy + oracle labeler + review CLI; `features.py`;
`learned.py` trained and calibrated; `policy.py` can select judge or learned.
*Accept:* labeled dataset built and split by incident; XGBoost verifier reports AUC + ECE on held-out
incidents; both verifiers swappable via config.

**P4 — Eval + Pareto + ablations.** Full harness, all five baselines, metrics, Pareto, ablation tables,
`notebooks/analysis.ipynb` generating report figures.
*Accept:* one command (`make eval`) reproduces the Pareto figure and ablation tables from scratch with a
fixed seed set. **This is the reproducibility check the checklist demands.**

**P5 — Gateway + observability + demo.** Dockerized FastAPI gateway, Prometheus metrics, Grafana dashboard,
React triage console showing the live loop (incident → proposed action → verdict → outcome).
*Accept:* `make demo` brings up the console + Grafana; a live incident flows through the loop on screen.

**Cluster integration (parallel, non-blocking):** implement `aiopslab_adapter.py` / `itbench_adapter.py`
against the same ABC once offline is solid. If cluster setup slips, the offline path still gives you a
complete, defensible Review 2 and Final.

---

## 9. `CLAUDE.md` (put this at repo root so Claude Code follows conventions)

```markdown
# Project conventions for Claude Code

## Golden rules
- The LLM is an UNTRUSTED PLANNER. No proposed action may reach `executor.run(dry_run=False)`
  without passing `verifier.policy.verify(...)`. Never bypass the verifier "for testing".
- `auto_execute` defaults to FALSE everywhere. Real apply requires an explicit config flag.
- Every cross-module payload is a Pydantic model from `src/sentinel/schemas`. No loose dicts across
  module boundaries.
- The system MUST run end-to-end with `OfflineEnvAdapter` and zero Kubernetes. Never make a core
  module import a cluster client at module top-level.

## Build order
Follow ARCHITECTURE_BLUEPRINT.md phases P0→P5. Do not start a phase until the prior phase's
acceptance criteria pass. Write the tests in the same commit as the code.

## Style
- Python 3.11, ruff + black, type hints required, functions <50 lines where reasonable.
- One reason per verdict `reasons[]` entry; keep them human-readable (they show in the console).
- Store every run: no experiment result exists unless it's a RunRecord row in DuckDB.

## Reproducibility
- All randomness seeded from config. `config_hash` recorded on every RunRecord.
- `make eval` must regenerate every figure from scratch. If a figure can't be regenerated, it's a bug.

## Don't
- Don't add a heavy agent framework; keep the ReAct loop in-repo and readable.
- Don't invent metrics; use the ones in eval/metrics.py.
- Don't let the diagnosis agent and the verifier share state or prompts — they must be independent.
```

---

## 10. Suggested first Claude Code prompts

Run these in order (one phase per session keeps context clean):

1. *"Read ARCHITECTURE_BLUEPRINT.md and CLAUDE.md. Scaffold Phase P0: repo layout, pyproject, all
   Pydantic schemas in src/sentinel/schemas, the OfflineEnvAdapter, 6 incident fixtures with oracles,
   Makefile, and passing tests for schemas + envelope. Stop at the P0 acceptance criteria and show me
   `make offline` output."*
2. *"Phase P1: implement the ReAct diagnosis agent with the four telemetry tools and propose.py, plus
   the dry-run executor and the gateway stub with token accounting. Add tests. Meet P1 acceptance."*
3. *"Phase P2: implement envelope.py, llm_judge.py, policy.py, the orchestrator loop, and the DuckDB
   store. Include a destructive-action fixture that must be blocked. Meet P2 acceptance and show a live
   end-to-end run on the offline fixtures."*
4. …continue P3–P5 the same way.

---

## 11. Risk register (carry into Review 1)

| Risk | Mitigation (built into this design) |
|------|--------------------------------------|
| Kubernetes / AIOpsLab setup slips | Offline adapter is the primary path; cluster is additive, same ABC |
| "Unsafe action" ground truth disputed | Explicit taxonomy + oracle-derived + human-reviewed gold set + traceability |
| Novelty challenged (guardrails are crowded) | Framed narrowly: operational-correctness verification on AIOps benchmarks, not adversarial safety |
| Verifier just memorizes fault families | Split by incident; report calibration; ablate signals |
| Cost blowup from LLM calls | Gateway token/cost accounting; offline caching of agent proposals for eval reruns |
| Not reproducible | Every run is a seeded DuckDB row; `make eval` regenerates all figures |

---

## 12. What this buys you at each review

- **Review 1:** architecture diagram (§1), module contracts (§5), dataset + baselines + metrics locked,
  risk register (§11).
- **Review 2:** P2 gives a live-demoable core module + real numbers from DuckDB + started ablations +
  reproducible-from-repo pipeline.
- **Final:** P4/P5 give the full Pareto, ablation tables against 5 baselines, live console demo, and a
  defensible novelty story you can defend in viva ("why verification, why AIOps, why this trade-off").
