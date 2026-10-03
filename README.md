# sentinel-remediate

Safety-gated LLM auto-remediation agent for AIOps. A pre-execution **verifier** sits between an LLM
diagnosis agent's proposed remediation actions and an environment's control plane, gating what's
allowed to execute and producing a measured safety ↔ autonomy trade-off.

Full design: [ARCHITECTURE_BLUEPRINT.md](ARCHITECTURE_BLUEPRINT.md). Claude Code conventions:
[CLAUDE.md](CLAUDE.md). Current build status: [PROGRESS.md](PROGRESS.md).

## Status

Phases **P0–P5** are implemented and run end to end with **zero Kubernetes and no API key**: the
diagnosis agent (an LLM ReAct agent, or a seeded simulated planner for offline runs), the layered
verifier (deterministic envelope → LLM judge and/or learned XGBoost verifier, combined by a τ
threshold), the orchestrator loop, a DuckDB run store, the evaluation harness, and the live triage
console. Details and what still needs a human, API spend or Docker: [PROGRESS.md](PROGRESS.md).

Headline offline result (`make eval`, 41 incidents × 5 seeds, τ = 0.5): the share of runs in which a
**destructive action reached execution** falls from 33% (ungated agent) and 21% (envelope only) to
**1%** (envelope + learned verifier). Read it with the caveats in `runs/eval/results.md`: the
proposals come from a simulated planner, and most labels are rule-derived.

## Setup

Requires Python 3.11+.

```bash
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -e ".[dev]"
```

(`make setup` runs the same thing if you have `make` available — e.g. via Git Bash / WSL / `choco
install make` on Windows. Every target below also has a plain `python`/`pytest` equivalent if you
don't have `make`.)

## Run it

| Command | What it does | Plain equivalent |
|---|---|---|
| `make test` | ~620 tests (~15 s) | `pytest -q` |
| `make agent` | P1: a structured proposal + dry-run result for all 41 incidents; real apply refused | `python scripts/agent_demo.py` |
| `make run VARIANT=learned` | P2: end-to-end runs into DuckDB, label × decision table | `python scripts/run_offline.py --variant learned` |
| `make train` | P3: cross-fitted learned verifier + out-of-fold AUC/ECE vs a type-only baseline | `python scripts/train_learned.py` |
| `make eval` | P4: retrain + 7,585 runs + every table and figure from scratch (~5 min) | `python scripts/run_eval.py` |
| `make demo-local` | P5: live gateway + console at http://localhost:5173, no Docker | `python scripts/demo_local.py` |
| `make demo` | P5: full Docker stack — console :4173, gateway :8080, Prometheus :9090, Grafana :3000 | `docker compose up --build` |
| `make e2e` | rehearses the live demo in headless Chromium against the real gateway | `python scripts/e2e_live_demo.py` |

Everything runs offline by default. The LLM-backed pieces (the ReAct agent, the LLM judge and the
`combined` variant) need Anthropic credentials and spend money: `make eval WITH_LLM=1`, or
`AGENT=react make agent`. LLM calls are cached on disk (`runs/llm_cache`), so reruns are free.

`make eval` writes `runs/eval/results.md` (tables with 95% bootstrap CIs) and `runs/eval/figures/`
(Pareto, prevention partition, calibration, agent-quality ablation); `notebooks/analysis.ipynb` reads
the same code.

### Triage console (`frontend/`)

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 — mock mode (MSW), zero backend required
npm run dev:live     # live mode: proxies /api to the gateway on :8080 (start it with `make gateway`)
```

Mock mode's Results screen shows a measured snapshot of `make eval` (`make mock-results` refreshes
it). The header shows which mode you are in. Demo walkthrough: [FRONTEND_BLUEPRINT.md §9](FRONTEND_BLUEPRINT.md);
`make e2e` checks it end to end (happy path on `bad-rollout-latency`; on `itbench-sre-scenario-12` the
envelope passes a destructive `cordon_node` and the learned layer blocks it).

## Repository layout

See [ARCHITECTURE_BLUEPRINT.md §3](ARCHITECTURE_BLUEPRINT.md#3-repository-layout) for the full,
annotated layout. In short:

- `src/sentinel/schemas/` — every cross-module payload (Pydantic v2). Read this first.
- `src/sentinel/env/` — `EnvAdapter` ABC; `offline_adapter.py` is the fully-implemented, cluster-free
  path; `aiopslab_adapter.py` / `itbench_adapter.py` are stubs for later cluster integration.
- `src/sentinel/verifier/` — the project's contribution: `envelope.py` (deterministic gate),
  `llm_judge.py` (v1, fail-closed), `learned.py` + `features.py` (v2, cross-fitted XGBoost), and
  `policy.py`, which combines them (envelope AND risk < τ, every layer reported).
- `src/sentinel/agent/` (ReAct + simulated planner), `executor/` (golden rules enforced in code),
  `orchestrator/` (the loop), `labeling/` (labels with provenance, review CLI), `eval/` (metrics,
  runner, Pareto, ablations, report, figures), `store/` (DuckDB), `gateway/` (FastAPI: console API
  with SSE, `/chat`, `/metrics`), `observability/` (Prometheus).
- `fixtures/incidents/` — 6 hand-built offline incidents plus 35 converted from the public ITBench-Lite
  SRE scenarios (`itbench-sre-scenario-*.json`, see [Data sources](#data-sources)). Each has an oracle
  with labeled example actions across the `correct` / `ineffective` / `destructive` /
  `out_of_envelope` taxonomy from blueprint §6.1.
- `config/action_envelope.yaml` — the allow-listed action types + param schemas the envelope verifier
  enforces.
- `tests/` — one test module per component; the suite never needs the network, a cluster, an API
  key or the raw ITBench download.

## Data sources

The 35 `fixtures/incidents/itbench-sre-scenario-*.json` incidents are derived from IBM Research's
[ITBench-Lite](https://huggingface.co/datasets/ibm-research/ITBench-Lite) (Apache-2.0; attribution and
citation in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)). Only the compacted fixture JSON is
committed; to regenerate it from the raw snapshots:

```bash
make fetch-itbench      # ~14 GB into data/ (gitignored): small files + logs/traces + alerted-service metrics
make convert-itbench    # data/ITBench-Lite/... -> fixtures/incidents/itbench-sre-scenario-*.json
```

Labels are **not** all benchmark ground truth. Each `oracle.labeled_actions[]` entry carries a
`provenance` (`itbench_derived` = mapped from ITBench's `recommended_actions`; `converter_synthesized` =
generated by this project's rules) and `needs_review: true` until a human reviews it. ITBench remedies
that match no allow-listed action are kept verbatim in `oracle.unmapped_recommendations[]` rather than
forced into the nearest type. The mapping rules live in
[config/itbench_action_mapping.yaml](config/itbench_action_mapping.yaml); the design and its limits are in
[docs/tasks/itbench_converter_spec.md](docs/tasks/itbench_converter_spec.md).

## Build order

Build strictly phase by phase, per [ARCHITECTURE_BLUEPRINT.md §8](ARCHITECTURE_BLUEPRINT.md#8-phased-build-plan-with-acceptance-criteria)
and the golden rules in [CLAUDE.md](CLAUDE.md). Don't start P1 until P0's acceptance criteria (above)
pass. The suggested Claude Code prompts for each phase are in
[ARCHITECTURE_BLUEPRINT.md §10](ARCHITECTURE_BLUEPRINT.md#10-suggested-first-claude-code-prompts).
