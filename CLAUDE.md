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
Follow [ARCHITECTURE_BLUEPRINT.md](ARCHITECTURE_BLUEPRINT.md) phases P0→P5 (see [PROGRESS.md](PROGRESS.md)
for current status). Do not start a phase until the prior phase's acceptance criteria pass. Write the
tests in the same commit as the code.

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
