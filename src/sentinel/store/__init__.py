# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Store package: run persistence in DuckDB.
# No experiment result exists unless it is stored here.
"""Run persistence: DuckDB over Parquet, one row per StepRecord/RunRecord. Phase P2 — see PROGRESS.md."""
