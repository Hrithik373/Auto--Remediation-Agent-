# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Labeling package: ground-truth labels (correct / ineffective / destructive / out_of_envelope).
# Produces the training data for the learned verifier and the labels used by eval metrics.
"""Ground-truth labeling pipeline for the learned verifier. Phase P3 — see PROGRESS.md and
ARCHITECTURE_BLUEPRINT.md §6.1.

The label taxonomy (correct | ineffective | destructive | out_of_envelope) is already exercised by
the offline fixtures (fixtures/incidents/*.json `oracle.labeled_actions[].label`) -- schema.py in
Phase P3 formalizes it as the canonical Python type the oracle_labeler/review_cli/features modules
share.
"""
