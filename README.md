# sentinel-remediate

Safety-gated LLM auto-remediation agent for AIOps. A pre-execution **verifier** sits between an LLM
diagnosis agent's proposed remediation actions and an environment's control plane, gating what's
allowed to execute and producing a measured safety ↔ autonomy trade-off.

Full design: [ARCHITECTURE_BLUEPRINT.md](ARCHITECTURE_BLUEPRINT.md). Claude Code conventions:
[CLAUDE.md](CLAUDE.md). Current build status: [PROGRESS.md](PROGRESS.md).

## Status

Phase **P0** is implemented: Pydantic schemas, the offline environment adapter, and the deterministic
envelope verifier — the whole pipeline runs and is testable with **zero Kubernetes / zero cluster**.
Phases P1–P5 exist as typed interface stubs (see [PROGRESS.md](PROGRESS.md)) ready to be filled in
phase by phase, per the blueprint's build order.

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

```bash
make test       # == pytest -q
make offline    # == python scripts/offline_demo.py — loads a fixture incident, prints its context,
                 #    and runs the envelope verifier against a correct and a destructive sample action
```

Expected `make offline` output: an `IncidentContext` summary for `pod-crashloop`, then an `allow`
verdict for the fixture's labeled-`correct` action and a `block` verdict for its labeled-`destructive`
action, sourced from `fixtures/incidents/pod-crashloop.json`.

`make eval` and `make demo` are placeholders until Phases P4 and P5 are built — they currently print a
message pointing back to [ARCHITECTURE_BLUEPRINT.md](ARCHITECTURE_BLUEPRINT.md).

## Repository layout

See [ARCHITECTURE_BLUEPRINT.md §3](ARCHITECTURE_BLUEPRINT.md#3-repository-layout) for the full,
annotated layout. In short:

- `src/sentinel/schemas/` — every cross-module payload (Pydantic v2). Read this first.
- `src/sentinel/env/` — `EnvAdapter` ABC; `offline_adapter.py` is the fully-implemented, cluster-free
  path; `aiopslab_adapter.py` / `itbench_adapter.py` are stubs for later cluster integration.
- `src/sentinel/verifier/` — the project's contribution. `envelope.py` (deterministic gate) is
  implemented; `llm_judge.py` (P2) and `learned.py` (P3) are stubs.
- `src/sentinel/agent/`, `executor/`, `orchestrator/`, `gateway/`, `labeling/`, `eval/`, `store/`,
  `observability/` — stubs for Phases P1–P5.
- `fixtures/incidents/` — 6 hand-built offline incidents, each with an oracle (resolution condition +
  hand-labeled example actions across the `correct` / `ineffective` / `destructive` /
  `out_of_envelope` taxonomy from blueprint §6.1).
- `config/action_envelope.yaml` — the allow-listed action types + param schemas the envelope verifier
  enforces.
- `tests/` — `test_schemas.py` and `test_envelope.py` are real; the rest are phase-gated placeholders
  (`pytest.skip`) that turn into real tests as each phase lands.

## Build order

Build strictly phase by phase, per [ARCHITECTURE_BLUEPRINT.md §8](ARCHITECTURE_BLUEPRINT.md#8-phased-build-plan-with-acceptance-criteria)
and the golden rules in [CLAUDE.md](CLAUDE.md). Don't start P1 until P0's acceptance criteria (above)
pass. The suggested Claude Code prompts for each phase are in
[ARCHITECTURE_BLUEPRINT.md §10](ARCHITECTURE_BLUEPRINT.md#10-suggested-first-claude-code-prompts).
