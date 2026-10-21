# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Context package: turns raw incident telemetry into compact text an LLM can read.
# Shared by the agent and the LLM judge (each renders its own prompt from it).
"""Telemetry -> LLM context compaction. Phase P1 — see PROGRESS.md."""
