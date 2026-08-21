# Analysis notebooks (Phase P4)

`analysis.ipynb` will read RunRecords from the DuckDB store (`src/sentinel/store/duckdb_store.py`,
Phase P2) and generate the report figures: the risk-autonomy Pareto curve and ablation tables from
[ARCHITECTURE_BLUEPRINT.md §7](../ARCHITECTURE_BLUEPRINT.md#7-evaluation-harness-drives-every-figure-in-the-report).

Not created yet — see [PROGRESS.md](../PROGRESS.md). Per CLAUDE.md's reproducibility rule, every
figure in it must be regeneratable from scratch via `make eval`.
