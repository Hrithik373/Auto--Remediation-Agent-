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

## Frontend conventions (sentinel-console)
See [FRONTEND_BLUEPRINT.md](FRONTEND_BLUEPRINT.md) for the full spec (Phase P5).
- Types in src/api/types.ts are GENERATED from Pydantic (make types). Never hand-edit them.
  If the UI needs a field, add it to the Pydantic schema first, then regenerate.
- The frontend must build and run fully against MSW mocks with the backend down (mock mode).
  Never let a component hard-require a live endpoint to render.
- Color means decision everywhere: use lib/decisionColors.ts. Never hardcode allow/block colors.
  Chart series colors are a separate, validated categorical set (dataviz skill) — never reuse a
  decision/status hue for a chart series identity, and never pick chart colors without running
  scripts/validate_palette.js against the console's actual surface first.
- Anything a machine emitted (logs, params, action_type, IDs, risk scores) renders in monospace.
- The live run is an EventSource, NOT a TanStack Query. Do not poll for step updates.
- No localStorage/sessionStorage. UI state lives in Zustand; server state in TanStack Query.
- VerdictCard must always show ALL layers (graying out inactive ones), never just the final decision —
  the layered view is the project's contribution and must stay visible.
