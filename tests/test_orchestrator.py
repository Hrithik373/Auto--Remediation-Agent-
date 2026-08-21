"""Orchestrator loop tests -- Phase P2 (blueprint §5, "core module demoed live").

Stays skipped until src/sentinel/orchestrator/loop.py is implemented; see PROGRESS.md. The P2
acceptance criteria this should eventually assert: an end-to-end run on offline fixtures produces
RunRecords, a deliberately-destructive fixture action is blocked, a correct action is allowed, and
results are queryable from DuckDB.
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="Phase P2: Orchestrator not implemented yet. See PROGRESS.md.")
def test_orchestrator_resolves_incident_via_correct_action(): ...


@pytest.mark.skip(reason="Phase P2: Orchestrator not implemented yet. See PROGRESS.md.")
def test_orchestrator_blocks_destructive_action_before_execution(): ...


@pytest.mark.skip(reason="Phase P2: Orchestrator not implemented yet. See PROGRESS.md.")
def test_orchestrator_writes_run_record_to_store(): ...
