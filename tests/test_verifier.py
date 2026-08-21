"""LLMJudgeVerifier / LearnedVerifier / CombinedPolicy tests -- Phases P2/P3.

EnvelopeVerifier (Phase P0) is covered in test_envelope.py, not here. These stay skipped until the
corresponding phase lands (see PROGRESS.md); replace the skip with real assertions as each module in
src/sentinel/verifier/{llm_judge,learned,policy}.py is implemented.
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="Phase P2: LLMJudgeVerifier not implemented yet. See PROGRESS.md.")
def test_llm_judge_verifier_blocks_destructive_action(): ...


@pytest.mark.skip(reason="Phase P3: LearnedVerifier not implemented yet. See PROGRESS.md.")
def test_learned_verifier_reports_calibrated_risk(): ...


@pytest.mark.skip(reason="Phase P2: CombinedPolicy not implemented yet. See PROGRESS.md.")
def test_combined_policy_requires_envelope_pass_and_score_below_threshold(): ...
