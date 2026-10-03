"""Turns the diagnosis agent's final reasoning step into a schema-valid ProposedAction (blueprint §3).

Kept separate from react.py so the emission/parsing contract is independently testable. Parsing is
strict -- a malformed proposal raises ProposalParseError (fed back to the agent to retry); it is never
"repaired" into some action the model didn't actually state.
"""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from sentinel.schemas.action import ProposedAction

_FINAL_MARKER = re.compile(r"final answer\s*:", re.IGNORECASE)


class ProposalParseError(ValueError):
    """The model's final answer was not a single valid ProposedAction JSON object."""


def _first_json_object(text: str) -> dict:
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ProposalParseError("no JSON object found in the final answer")


def parse_proposed_action(raw_model_output: str) -> ProposedAction:
    """Parse the JSON object after 'Final Answer:' (or the first JSON object if no marker)."""
    marker = _FINAL_MARKER.search(raw_model_output)
    text = raw_model_output[marker.end() :] if marker else raw_model_output
    obj = _first_json_object(text)
    try:
        return ProposedAction.model_validate(obj)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        raise ProposalParseError(f"final answer is not a valid ProposedAction ({problems})") from exc
