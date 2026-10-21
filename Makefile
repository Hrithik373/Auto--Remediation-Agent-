.PHONY: observability observability-down setup test offline agent train review run eval report demo demo-local gateway e2e report-pdf frontend-guide blueprint mindmap mock-results demo lint fmt clean types frontend-dev frontend-build fetch-itbench convert-itbench

setup:
	pip install -e ".[dev]"

test:
	pytest -q

offline:
	python scripts/offline_demo.py

# Phase P1 acceptance: a structured proposal + dry-run result for every fixture; real apply refused.
# AGENT=react uses the LLM ReAct agent (needs Anthropic credentials); default is config agent.kind.
agent:
	python scripts/agent_demo.py $(if $(AGENT),--agent $(AGENT),)

# Phase P3 acceptance: labeled dataset split by incident; cross-fitted XGBoost verifier with
# out-of-fold AUC/ECE (and the type-only baseline it must beat). Writes runs/models/.
train:
	python scripts/train_learned.py

# Human review of needs_review labels: make review FIXTURE=fixtures/incidents/<id>.json REVIEWER=<name>
review:
	python -m sentinel.labeling.review_cli $(FIXTURE) --reviewer $(or $(REVIEWER),reviewer)

# Phase P2 acceptance: end-to-end runs on every fixture -> RunRecords in DuckDB.
# VARIANT = none | envelope | llm_judge | learned | combined (llm_judge needs Anthropic credentials).
VARIANT ?= envelope
run:
	python scripts/run_offline.py --variant $(VARIANT)

# ITBench-Lite -> fixtures (docs/tasks/itbench_converter_spec.md). The fetch is a separate, one-time
# ~14 GB download into data/ (gitignored); convert never downloads.
ITBENCH_SRC ?= $(firstword $(wildcard data/ITBench-Lite/snapshots/sre/v0.2-*))

fetch-itbench:
	HF_HUB_DISABLE_XET=1 python scripts/fetch_itbench.py --with-telemetry

convert-itbench:
	python scripts/convert_itbench.py --source-dir $(ITBENCH_SRC)

# Phase P4 acceptance: retrain + rerun every cell + rebuild every table and figure FROM SCRATCH
# (~5 min, offline). WITH_LLM=1 adds the LLM judge / ReAct baselines -- these spend API money.
eval:
	python scripts/run_eval.py $(if $(WITH_LLM),--with-llm,)

# Rebuild runs/eval/{results.md,results.json,figures/} from DuckDB without rerunning anything.
report:
	python scripts/run_eval.py --report-only

# Phase P5e: the full stack in Docker -- console :4173, gateway :8080, Prometheus :9090, Grafana :3000.
demo:
	docker compose up --build

# The live demo without Docker: gateway + console (live mode, :5173). No Prometheus/Grafana.
demo-local:
	python scripts/demo_local.py

# Prometheus :9090 + Grafana :3000 in Docker, scraping a natively running gateway (demo-local or
# scripts/start_backend.ps1). Fills the console's Observability screen. Stop: make observability-down
observability:
	docker compose -f docker-compose.observability.yml up -d

observability-down:
	docker compose -f docker-compose.observability.yml down

# Just the gateway (console API + /chat + /metrics) on :8080 against the offline env.
gateway:
	SENTINEL_CONFIG=config/offline_eval.yaml uvicorn sentinel.gateway.app:app --app-dir src --port 8080

# Rehearse the live demo (FRONTEND_BLUEPRINT.md §9) in headless Chromium against the real gateway.
# Needs: pip install playwright && python -m playwright install chromium
e2e:
	python scripts/e2e_live_demo.py

# The architecture & evaluation report (docs/architecture_report.pdf), filled from `make eval` outputs
# and `make e2e` screenshots. Title-page details: docs/report/report_meta.yaml.
report-pdf:
	python scripts/build_report.py

# The frontend guide (docs/frontend_guide.pdf). CAPTURE=1 refreshes its screenshots from the running
# console first (needs `make demo-local` up).
frontend-guide:
	python scripts/build_frontend_guide.py $(if $(CAPTURE),--capture,)

# The project blueprint (docs/project_blueprint.pdf): every file explained simply. Fails if any tracked
# file lacks a description -- add one in scripts/build_blueprint.py when you add a file.
blueprint:
	python scripts/build_blueprint.py

# The project mind map (docs/project_mindmap.pdf): the whole project on one A3 page.
mindmap:
	python scripts/build_mindmap.py

# Snapshot `make eval`'s results into the console's mock layer (frontend/src/mock/experiments.json).
mock-results:
	python scripts/export_mock_results.py

# Regenerates frontend/src/api/types.ts from src/sentinel/schemas/*.py. Never hand-edit that file --
# see FRONTEND_BLUEPRINT.md §5.3 and CLAUDE.md's frontend addendum.
types:
	python scripts/export_schemas.py
	cd frontend && node scripts/gen-types.mjs

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

lint:
	ruff check src tests scripts
	black --check src tests scripts

fmt:
	ruff check --fix src tests scripts
	black src tests scripts

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} \;
	rm -rf .pytest_cache build dist *.egg-info
