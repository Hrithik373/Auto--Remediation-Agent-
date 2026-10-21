# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Package root of the backend. Every module lives under this package.
# Holds no logic; see the subpackages (agent, verifier, orchestrator, gateway, eval ...).
"""sentinel-remediate: safety-gated LLM auto-remediation agent for AIOps.

See ARCHITECTURE_BLUEPRINT.md at the repo root for the full design and PROGRESS.md for what's
implemented vs. stubbed.
"""

__version__ = "0.1.0"
