# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Environment package: the only code allowed to touch a benchmark or cluster.
# Offline fixtures are fully implemented; AIOpsLab and ITBench adapters are stubs.
"""Environment adapters. EnvAdapter (base.py) is the only interface allowed to touch a benchmark —
see ARCHITECTURE_BLUEPRINT.md §5. OfflineEnvAdapter is fully implemented (Phase P0); the
AIOpsLab/ITBench adapters are stubs pending cluster integration.
"""

from sentinel.env.base import EnvAdapter
from sentinel.env.offline_adapter import OfflineEnvAdapter

__all__ = ["EnvAdapter", "OfflineEnvAdapter"]
