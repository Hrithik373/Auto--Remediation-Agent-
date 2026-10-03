.PHONY: setup test offline eval demo lint fmt clean types frontend-dev frontend-build fetch-itbench convert-itbench

setup:
	pip install -e ".[dev]"

test:
	pytest -q

offline:
	python scripts/offline_demo.py

# ITBench-Lite -> fixtures (docs/tasks/itbench_converter_spec.md). The fetch is a separate, one-time
# ~14 GB download into data/ (gitignored); convert never downloads.
ITBENCH_SRC ?= $(firstword $(wildcard data/ITBench-Lite/snapshots/sre/v0.2-*))

fetch-itbench:
	HF_HUB_DISABLE_XET=1 python scripts/fetch_itbench.py --with-telemetry

convert-itbench:
	python scripts/convert_itbench.py --source-dir $(ITBENCH_SRC)

# Placeholders until their phases land — see PROGRESS.md / ARCHITECTURE_BLUEPRINT.md §8.
eval:
	@echo "Phase P4 (eval harness) is not implemented yet. See ARCHITECTURE_BLUEPRINT.md §7-8."

# Phase P5a/b: the console runs fully against MSW mocks today. P5e (gateway+Grafana+console together)
# is not implemented yet — see FRONTEND_BLUEPRINT.md §10.
demo: frontend-dev

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
