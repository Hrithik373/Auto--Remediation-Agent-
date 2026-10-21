# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Agent package: the diagnosis side that reads telemetry and PROPOSES one remediation.
# It never executes anything and shares no state or prompts with the verifier package.
"""Diagnosis agent (ReAct loop over telemetry tools, emits ProposedAction). Phase P1 — see PROGRESS.md.

Per CLAUDE.md: the diagnosis agent is an UNTRUSTED PLANNER and must not share state or prompts with
the verifier package.
"""
