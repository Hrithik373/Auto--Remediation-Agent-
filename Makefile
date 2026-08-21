.PHONY: setup test offline eval demo lint fmt clean

setup:
	pip install -e ".[dev]"

test:
	pytest -q

offline:
	python scripts/offline_demo.py

# Placeholders until their phases land — see PROGRESS.md / ARCHITECTURE_BLUEPRINT.md §8.
eval:
	@echo "Phase P4 (eval harness) is not implemented yet. See ARCHITECTURE_BLUEPRINT.md §7-8."

demo:
	@echo "Phase P5 (gateway + console demo) is not implemented yet. See ARCHITECTURE_BLUEPRINT.md §8."

lint:
	ruff check src tests scripts
	black --check src tests scripts

fmt:
	ruff check --fix src tests scripts
	black src tests scripts

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} \;
	rm -rf .pytest_cache build dist *.egg-info
