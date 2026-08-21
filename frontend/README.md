# Triage console (Phase P5)

React + Vite frontend showing the live orchestrator loop: incident feed -> proposed action -> verdict
-> outcome. Not scaffolded yet — see [PROGRESS.md](../PROGRESS.md) and
[ARCHITECTURE_BLUEPRINT.md §8](../ARCHITECTURE_BLUEPRINT.md#8-phased-build-plan-with-acceptance-criteria)
(Phase P5) for what it needs to do: `make demo` should bring this up alongside Grafana and stream a
live incident through the loop.

`src/` is a placeholder directory reserved for the Vite app until P5 scaffolds it (`npm create
vite@latest . -- --template react-ts` from this directory is the expected starting point).
