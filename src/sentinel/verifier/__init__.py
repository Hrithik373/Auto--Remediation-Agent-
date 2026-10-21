# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Verifier package (the project's contribution): gates every proposed action before execution.
# Layers: envelope (rules), llm_judge (LLM), learned (XGBoost), combined by policy.py.
"""The project's contribution: a pre-execution verification layer that gates ProposedActions before
they reach EnvAdapter.apply_action(dry_run=False). See ARCHITECTURE_BLUEPRINT.md §6.

envelope.py (deterministic allow-list gate) is implemented in Phase P0. llm_judge.py (P2), learned.py
(P3), and the policy.py combinator (P2) are interface stubs — see PROGRESS.md.
"""

from sentinel.verifier.base import Verifier
from sentinel.verifier.envelope import EnvelopeVerifier

__all__ = ["Verifier", "EnvelopeVerifier"]
