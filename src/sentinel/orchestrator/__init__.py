# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Orchestrator package: the main loop diagnose -> propose -> VERIFY -> act / revise / escalate.
# Ties together the agent, the verifier policy and the executor.
"""The orchestrator loop: diagnose -> propose -> VERIFY -> act/revise/escalate. Phase P2 — see
PROGRESS.md and ARCHITECTURE_BLUEPRINT.md §5.
"""
