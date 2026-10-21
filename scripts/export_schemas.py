#!/usr/bin/env python
"""Exports Pydantic v2 JSON Schemas for `frontend/scripts/gen-types.mjs` to compile into
frontend/src/api/types.ts. Part of the `make types` / `npm run types` pipeline
(FRONTEND_BLUEPRINT.md §5.3, CLAUDE.md frontend addendum: "Never hand-edit [types.ts]. If the UI
needs a field, add it to the Pydantic schema first, then regenerate.").
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sentinel.schemas.action import ExecutionResult, ProposedAction  # noqa: E402
from sentinel.schemas.assistant import (  # noqa: E402
    AssistantInfo,
    ChatReply,
    ChatRequest,
    IncidentEntities,
    ScenarioJudgement,
    ScenarioRequest,
    VerdictExplanation,
)
from sentinel.schemas.incident import IncidentContext, Telemetry  # noqa: E402
from sentinel.schemas.run import RunRecord, StepRecord  # noqa: E402
from sentinel.schemas.verdict import Verdict  # noqa: E402

# Every model the frontend consumes across api/incidents.ts, api/runs.ts, api/experiments.ts and
# api/assistant.ts (Phase P6, ASSISTANT_BLUEPRINT.md).
MODELS = [
    Telemetry,
    IncidentContext,
    ProposedAction,
    ExecutionResult,
    Verdict,
    StepRecord,
    RunRecord,
    ScenarioRequest,
    ScenarioJudgement,
    VerdictExplanation,
    ChatRequest,
    ChatReply,
    AssistantInfo,
    IncidentEntities,
]


def main() -> None:
    definitions: dict[str, dict] = {}

    for model in MODELS:
        # draft-07 `definitions` (not pydantic v2's default `$defs`) is what json-schema-to-typescript
        # expects for its multi-type `unreachableDefinitions` mode -- see gen-types.mjs.
        schema = model.model_json_schema(ref_template="#/definitions/{model}")
        nested = schema.pop("$defs", {})
        definitions[model.__name__] = schema
        for name, sub_schema in nested.items():
            definitions.setdefault(name, sub_schema)

    combined = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "SentinelSchemas",
        "type": "object",
        "definitions": definitions,
    }

    out_path = Path(__file__).resolve().parents[1] / "frontend" / "schemas" / "pydantic-schemas.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(combined, indent=2), encoding="utf-8")
    print(f"wrote {out_path} ({len(definitions)} definitions)")


if __name__ == "__main__":
    main()
