# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Evaluation package: runs incidents x seeds x verifier configs and reports the results.
# Driven by `make eval` (scripts/run_eval.py); everything is rebuilt from DuckDB.
"""Evaluation harness: runs incidents x seeds x config, computes metrics, draws the risk-autonomy
Pareto curve, runs ablations. Phase P4 — see PROGRESS.md and ARCHITECTURE_BLUEPRINT.md §7.
"""
