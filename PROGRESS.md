# Build status

Tracks which phase of [ARCHITECTURE_BLUEPRINT.md](ARCHITECTURE_BLUEPRINT.md) is implemented vs. scaffolded.
Update this file whenever a phase's acceptance criteria are met.

| Phase | Status | Notes |
|-------|--------|-------|
| P0 — Scaffold + schemas + offline env | ✅ Implemented | Schemas, `OfflineEnvAdapter`, deterministic `EnvelopeVerifier`, 6 fixtures, `make offline`, `make test` green. |
| P1 — Diagnosis agent + executor (dry-run) | 🔲 Stubbed only | `agent/`, `executor/` contain interfaces + `NotImplementedError`. |
| P2 — Verifier v1 (LLM-judge) + orchestrator | 🔲 Stubbed only | `verifier/llm_judge.py`, `verifier/policy.py`, `orchestrator/loop.py` are interfaces only. |
| P3 — Verifier v2 (learned) + labeling | 🔲 Stubbed only | `verifier/learned.py`, `verifier/features.py`, `labeling/` are interfaces only. |
| P4 — Eval harness + Pareto + ablations | 🔲 Stubbed only | `eval/` contains interfaces only. |
| P5 — Gateway + observability + demo | 🔲 Stubbed only | `gateway/`, `observability/`, `frontend/` are placeholders. |

## Verify P0 yourself

```bash
make setup
make test      # pytest: schemas + envelope tests
make offline   # loads fixtures/incidents/pod-crashloop.json and prints its IncidentContext
```

## Next step

Start a fresh session and run Claude Code prompt #2 from
[ARCHITECTURE_BLUEPRINT.md §10](ARCHITECTURE_BLUEPRINT.md#10-suggested-first-claude-code-prompts) to build P1.
