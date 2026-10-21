# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Assistant package (Phase P6): the chatbot that explains the system and the verifier's verdicts.
# It never decides and never executes: judgements come from verifier.policy, verify only.
"""sentinel-assistant -- see ASSISTANT_BLUEPRINT.md.

Independent of the diagnosis agent and the verifier: its own prompt, LLM client and ledger. It reads
verdicts as data and explains them; it is not a path to the executor.
"""
