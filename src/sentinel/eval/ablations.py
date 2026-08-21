"""Ablation runs required for Review 2 (blueprint §7): verifier off vs. on; envelope-only vs. +judge
vs. +learned; telemetry-signal ablation; tau sweep; model-size sweep. Phase P4.
"""

from __future__ import annotations

from sentinel.env.base import EnvAdapter


def run_ablations(env: EnvAdapter, incident_ids: list[str]) -> dict[str, list[dict]]:
    raise NotImplementedError(
        "eval.ablations.run_ablations is Phase P4 work. See ARCHITECTURE_BLUEPRINT.md §7, §8."
    )
