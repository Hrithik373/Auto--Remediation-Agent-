"""Reversibility helpers (blueprint §3) -- only for `reversible: true` types in config/action_envelope.yaml.

Rollback PLANS an inverse action; it never executes one. The inverse is itself a ProposedAction and
must go through verifier.policy and Executor.run like any other -- otherwise rollback would be a side
door around the golden rule ("no action reaches the executor without passing the verifier").
"""

from __future__ import annotations

from sentinel.schemas.action import ExecutionResult, ProposedAction


def plan_rollback(action: ProposedAction, result: ExecutionResult) -> ProposedAction | None:
    """The inverse of an executed action, or None when there is nothing to undo / no safe inverse.

    Deliberately conservative: an inverse is returned only when it is fully determined by the action
    itself. E.g. scale_deployment can't be inverted without the pre-change replica count, which the
    action doesn't carry -- guessing would itself be an unsafe action.
    """
    if not result.executed or result.dry_run:
        return None
    if action.action_type == "toggle_feature_flag" and isinstance(action.params.get("enabled"), bool):
        return action.model_copy(
            update={
                "params": {**action.params, "enabled": not action.params["enabled"]},
                "rationale": f"rollback of: {action.rationale}",
                "predicted_effect": f"restores flag '{action.params.get('flag')}' to its prior state",
            }
        )
    return None
