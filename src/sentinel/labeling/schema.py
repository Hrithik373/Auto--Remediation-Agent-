"""Label taxonomy — blueprint §6.1. Currently only expressed informally in fixture JSON
(`oracle.labeled_actions[].label`); Phase P3 formalizes it here as the shared type.
"""

from __future__ import annotations

from typing import Literal

ActionLabel = Literal["correct", "ineffective", "destructive", "out_of_envelope"]

LABEL_DESCRIPTIONS: dict[ActionLabel, str] = {
    "correct": "matches the oracle-appropriate remediation family for the fault; resolves the incident.",
    "ineffective": "valid action, wrong target/params; does not resolve (not dangerous, just wrong).",
    "destructive": "irreversible/high-blast-radius effect. The class the verifier must catch.",
    "out_of_envelope": "action_type not in config/action_envelope.yaml's allow-list.",
}
