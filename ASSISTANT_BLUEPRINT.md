# sentinel-assistant — Architecture Blueprint (Phase P6)

> Companion to `ARCHITECTURE_BLUEPRINT.md` and `FRONTEND_BLUEPRINT.md`. Codename: **`sentinel-assistant`**
> ("Ask Sentinel" in the console).

## 1. Purpose

A chatbot inside the triage console that can:

1. **Explain the system:** what each component does, how the verifier layers combine, what a metric
   means, and where the code lives.
2. **Judge a scenario:** given an incident and a proposed action, report whether the action would be
   **allowed, revised or blocked**, and why.
3. **Explain a past decision:** for any step of a stored run, say which layer decided, what the
   reasons were, how far the risk was from τ, and whether the verdict was right according to the
   ground-truth label.

## 2. Non-negotiables

These follow from the project's golden rules and are enforced in code and tests, not by convention.

| Rule | How it is enforced |
|---|---|
| **The assistant never decides.** Every allow/revise/block it reports comes from the real `verifier.policy.CombinedPolicy`. | Judgements are produced only by `assistant/scenarios.py` → `build_verifier(...).verify(...)`. The LLM receives the verdict as tool output. The reply's `judgement` field is filled from the tool result, never parsed from LLM text. |
| **The assistant never executes.** | `ScenarioJudgement.executed` is typed `Literal[False]`. No assistant module references `Executor` or `apply_action` (an AST test checks this). A runtime test verifies `apply_action` is never called during scenario evaluation. |
| **Independent of the agent and the judge.** | Own system prompt (`assistant/prompts.py`), own LLM client and `UsageLedger` (`models.assistant`, `models.assistant_provider`). It never sees the agent's conversation or the judge's prompt, only their recorded outputs. |
| **Runs fully offline.** | With no LLM credentials, or on any LLM error, `AssistantService` answers in **offline mode**: a deterministic intent router calls the same tools and composes a templated answer. The reply says which mode produced it. |
| **Grounded answers.** | Every factual answer is built from tool output. Doc answers carry `citations` (file + section). Scenario answers carry the full `Verdict` with all three layers. |
| **Typed boundaries.** | All payloads are Pydantic models in `schemas/assistant.py`; frontend types are regenerated with `make types`. |

## 3. Architecture

```
 Console  /assistant route
   ├─ ChatPanel ───────────── POST /api/assistant/chat ─────┐
   └─ ScenarioPanel ───────── POST /api/assistant/scenario ─┤
      (Triage "Ask why") ──── GET  /api/assistant/explain/{run}/{step}
                                                             ▼
                                         gateway/api.py  (assistant routes)
                                                             │
                                         assistant/service.py  AssistantService
                                         ├── LLM mode:  tool loop (assistant/loop.py)
                                         │     own prompt + own LLM client + ledger
                                         └── offline mode: intent router (assistant/router.py)
                                                             │  both call the SAME read-only tools
                                         assistant/tools.py  ▼
     ┌───────────────┬──────────────────┬──────────────────┬─────────────────┬──────────────────┐
  search_docs   get_incident   evaluate_scenario    explain_step      envelope_rules   eval_metrics
  knowledge.py  env adapter    scenarios.py         store + explain   action_envelope  results.json
  (docstrings,  (read only)    └─ CombinedPolicy    (stored Verdict)  .yaml
   blueprints)                    .verify() only
                                  + oracle label
                                  + counterfactuals
                                         │
                                  assistant/explain.py  ← deterministic: Verdict → VerdictExplanation
```

The explanation of a verdict is **deterministic** (`explain.py`): the same verdict always yields the
same headline, per-layer summaries, threshold margins and counterfactuals. The LLM (when present)
only phrases the answer around that material; the structured explanation is returned alongside, so
the UI never depends on LLM wording.

## 4. Components

| File | Responsibility |
|---|---|
| `schemas/assistant.py` | `ScenarioRequest`, `ScenarioJudgement`, `VerdictExplanation`, `LayerExplanation`, `Counterfactual`, `GroundTruth`, `ChatRequest`, `ChatReply`, `ToolCall`, `Citation`. |
| `assistant/entities.py` | Dropdown choices for the scenario form, per incident (see §7). |
| `assistant/knowledge.py` | Indexes module docstrings under `src/sentinel/` and the markdown sections of the blueprints, README and PROGRESS. Keyword (BM25-style) search that returns snippets with their source. No new dependencies. |
| `assistant/explain.py` | `explain_verdict(verdict, tau, ...)`. Works out which layer decided, a one-line headline, a plain-language summary per layer, the threshold margin, and threshold counterfactuals. |
| `assistant/scenarios.py` | `ScenarioEvaluator`. Builds the `ProposedAction`, runs the real policy for the chosen variant (verify only), attaches the oracle ground-truth label and assessment, and optionally re-verifies under the offline variants for comparison. |
| `assistant/tools.py` | The read-only tool registry. The LLM loop and the offline router share it, so both modes see the same facts. |
| `assistant/prompts.py` | The assistant's own system prompt. |
| `assistant/loop.py` | A small in-repo tool loop (the same Thought/Action/Final Answer text protocol as `agent/react.py`, with its own prompt). Capped at `assistant.max_tool_calls`. |
| `assistant/router.py` | The offline intent router: explain step → scenario → incident → envelope → metrics → docs. |
| `assistant/service.py` | `AssistantService.chat()` / `.scenario()` / `.explain_step()`. Chooses the mode, falls back to offline on any LLM failure, and assembles `ChatReply`. |
| `gateway/assistant_api.py` | `GET /api/assistant/info`, `POST /api/assistant/chat`, `POST /api/assistant/scenario`, `GET /api/assistant/explain/{run_id}/{step_idx}`. Shares `gateway/api.py`'s config, store and live runs. |
| `frontend/src/routes/AssistantRoute.tsx` | Chat on the left, scenario builder on the right. Judgements render with the existing `VerdictCard` (all layers visible) plus an `ExplanationCard`. Triage steps get an **Ask why** link that opens the chat with that run and step as context. Mock mode serves clearly labeled canned replies (`mock/assistant.ts`). |

## 5. How a verdict is explained (`explain.py`)

1. **Who decided.**
   - Envelope block: the envelope decided (hard gate; no τ changes it).
   - Allow with no secondary layer: the envelope's risk was below τ.
   - Allow with secondary layers: every active layer's risk was below τ. The layer with the highest
     risk is named as the closest to blocking.
   - Block or revise over τ: the secondary layer with the highest risk decided. It is revise only
     if a layer over τ asked for revise and none asked for block (mirrors `policy._decide`).
2. **Margins.** For a risk-decided verdict, the distance between the deciding score and τ, and the
   τ at which the decision flips: "would be blocked at τ ≤ 0.31" or "would be allowed only at
   τ > 0.82". A risk of 1.0 cannot be allowed by any τ.
3. **Layer summaries.** One sentence per layer. Inactive layers say so: they stay visible, as in
   the VerdictCard.
4. **Ground truth** (fixtures only). The oracle label (`labeling/oracle_labeler.py`) and its
   provenance, mapped onto the eval's own terms (`eval/metrics.py`):

   | Label | Allowed | Blocked or revised |
   |---|---|---|
   | destructive | missed (unsafe) | correct catch (counts toward bad-action-prevented) |
   | out_of_envelope | missed (unsafe) | correct catch (envelope) |
   | correct | correct allow | false block (counts toward false-block rate) |
   | ineffective | allowed, harmless but won't fix | blocked, harmless either way |

   Labels the converter synthesized or that are still marked `needs_review` are flagged as such.
5. **Variant comparison** (scenario only). The same action re-verified under `none`, `envelope`
   and `learned`, which are cheap and offline. The judge is only included when the requested
   variant already uses it, so a comparison never adds surprise LLM calls.

## 6. Chat modes

**Implied parameters.** A chat question rarely spells out every required param ("can we cordon
node-17?"). `evaluate_scenario` fills required target-like params (`service`, `deployment`,
`pod_name`, `node_name`, `configmap`) from the target, and `namespace` from the incident's usual
namespace, then reports exactly what it assumed. Without this the envelope would judge a malformed
action instead of the user's actual question. The scenario form (`POST /scenario`) never fills
anything: it judges exactly what was sent.

**LLM mode** (`assistant.enabled_llm: true` and the provider reachable):
`system = prompts.SYSTEM` plus the tool list. Each turn is either a tool call or a `Final Answer`.
The prompt requires: call `evaluate_scenario` before stating any judgement; never contradict or
"overrule" a verdict; quote layer reasons; say so when the judge failed closed; cite doc sources.
If the loop fails (parse errors, budget, provider error), the service answers offline and sets
`notice`.

**Offline mode** (always available):
`router.py` reads the last user message plus the request context (`incident_id`, `run_id`,
`step_idx`):
- "why" or "explain" with run context → `explain_step`.
- An action type from the envelope or a known out-of-envelope verb (`drain_node`, `delete_*`)
  plus an incident → `evaluate_scenario`.
- An incident id → `get_incident`.
- "envelope", "allowed actions" or "rule" → `envelope_rules`.
- "metric", "results" or "false block" → `eval_metrics`.
- Anything else → `search_docs`.

## 7. API contract

| Method | Path | Body / params | Returns |
|---|---|---|---|
| POST | `/api/assistant/chat` | `ChatRequest` | `ChatReply` |
| POST | `/api/assistant/scenario` | `ScenarioRequest` | `ScenarioJudgement` |
| GET | `/api/assistant/explain/{run_id}/{step_idx}` | — | `VerdictExplanation` |
| GET | `/api/assistant/entities/{incident_id}` | — | `IncidentEntities`: dropdown choices for the scenario form. Entity names from observable telemetry (topology, alert targets, pods in logs, namespaces) plus the parameter values of the incident's candidate actions. Values only: which candidate is correct or destructive is never exposed. |
| GET | `/api/assistant/info` | — | `AssistantInfo`: mode (llm/offline), why LLM mode is off, default variant, allow-listed actions with param specs (scenario form) |

None of these endpoints can execute an action or change a stored run.

## 8. Config (`config/default.yaml`)

```yaml
models:
  assistant: qwen/qwen3.8-27b
  assistant_provider: groq
assistant:
  enabled_llm: true          # false = always offline mode
  max_tool_calls: 5
  max_tokens: 1500
  docs: [ARCHITECTURE_BLUEPRINT.md, FRONTEND_BLUEPRINT.md, ASSISTANT_BLUEPRINT.md, README.md, PROGRESS.md]
  default_variant: learned   # offline-safe default for scenarios
```

## 9. Acceptance criteria

- `make test` covers the following:
  - explanation logic for every decision path (envelope block, allow, block over τ, revise, ungated);
  - the ground-truth assessment table;
  - scenario evaluation never calls `apply_action`;
  - no assistant module references the executor;
  - offline routing for each intent;
  - the LLM loop with a scripted client: a tool call, a final answer, and fallback on garbage;
  - the API endpoints.
- With the backend down, the console's `/assistant` route works against the MSW mocks.
- With no LLM key, `/api/assistant/chat` still answers (`mode: "offline"`).

## 10. Known limits

- Offline mode understands only simple phrasing. Use the scenario form for exact scenarios.
- The ground truth only exists for fixture incidents. A free-form scenario on an unknown target may
  have no label (`unknown`).
- Explanations of the learned layer are its top feature contributions. They are associative, not
  causal.
