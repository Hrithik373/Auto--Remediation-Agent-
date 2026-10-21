# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Executor package: the only way a proposed action is applied (dry-run or real).
# Real applies need an 'allow' verdict and auto_execute=true; both are enforced in code.
"""Executor: dry-run | apply. Phase P1 — see PROGRESS.md.

Golden rule (CLAUDE.md): no ProposedAction may reach Executor.run(dry_run=False) without first
passing verifier.policy.verify(...); auto_execute defaults to False everywhere.
"""
