"""Executor: dry-run | apply. Phase P1 — see PROGRESS.md.

Golden rule (CLAUDE.md): no ProposedAction may reach Executor.run(dry_run=False) without first
passing verifier.policy.verify(...); auto_execute defaults to False everywhere.
"""
