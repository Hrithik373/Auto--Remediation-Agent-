"""Evaluation harness metric tests -- Phase P4 (blueprint §7).

Stays skipped until src/sentinel/eval/metrics.py is implemented; see PROGRESS.md. Per CLAUDE.md,
these ARE the canonical metric definitions -- don't invent new ones elsewhere in the report/notebook.
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="Phase P4: eval.metrics not implemented yet. See PROGRESS.md.")
def test_resolution_rate(): ...


@pytest.mark.skip(reason="Phase P4: eval.metrics not implemented yet. See PROGRESS.md.")
def test_bad_action_prevented_rate(): ...


@pytest.mark.skip(reason="Phase P4: eval.metrics not implemented yet. See PROGRESS.md.")
def test_false_block_rate(): ...


@pytest.mark.skip(reason="Phase P4: eval.metrics not implemented yet. See PROGRESS.md.")
def test_net_safe_resolutions(): ...
