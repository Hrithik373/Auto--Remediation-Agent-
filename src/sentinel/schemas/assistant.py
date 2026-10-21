# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# Contracts for the assistant (chatbot): scenario judgements, verdict explanations, chat turns.
# Served by the /api/assistant/* routes; the console's Assistant route renders them.
"""Assistant contracts (ASSISTANT_BLUEPRINT.md §4).

The assistant explains verdicts; it never produces one. A ScenarioJudgement's `verdict` is the real
verifier policy's output, and `executed` is typed Literal[False] so no payload can ever claim the
assistant ran an action.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from sentinel.schemas.action import ProposedAction
from sentinel.schemas.verdict import Verdict

Variant = Literal["none", "envelope", "llm_judge", "learned", "combined"]
Decision = Literal["allow", "block", "revise"]


class ScenarioRequest(BaseModel):
    """'What would the verifier say if the agent proposed THIS on THAT incident?'"""

    incident_id: str = Field(min_length=1)
    action_type: str = Field(min_length=1)
    target: str = Field(min_length=1)
    params: dict = Field(default_factory=dict)
    rationale: str = Field(default="", description="optional; a neutral template is used when empty")
    variant: Variant = "learned"
    tau: float = Field(default=0.5, ge=0.0, le=1.0)
    compare_variants: bool = Field(
        default=True, description="also re-verify under the offline variants (none, envelope, learned)"
    )


class LayerExplanation(BaseModel):
    verifier: Literal["envelope", "llm_judge", "learned"]
    decision: Literal["allow", "block", "revise", "skipped"]
    risk_score: float | None = None
    over_threshold: bool | None = Field(
        default=None, description="secondary layers only: risk_score >= tau. None for envelope/skipped."
    )
    summary: str = Field(description="one plain-language sentence")
    reasons: list[str] = Field(default_factory=list)


class Counterfactual(BaseModel):
    kind: Literal["threshold", "variant"]
    description: str
    decision: Decision | None = Field(default=None, description="the decision under this alternative")


AssessmentKind = Literal[
    "correct_catch",
    "missed",
    "correct_allow",
    "false_block",
    "harmless_allowed",
    "harmless_blocked",
    "unknown",
]


class GroundTruth(BaseModel):
    """The oracle label for this action (eval-only ground truth) and what it says about the verdict."""

    label: Literal["correct", "ineffective", "destructive", "out_of_envelope"] | None = None
    provenance: str = ""
    assessment: AssessmentKind = "unknown"
    note: str = ""


class VerdictExplanation(BaseModel):
    decision: Decision
    decided_by: Literal["envelope", "llm_judge", "learned", "none"]
    headline: str
    layers: list[LayerExplanation]
    tau: float
    threshold_note: str
    counterfactuals: list[Counterfactual] = Field(default_factory=list)
    ground_truth: GroundTruth | None = None


class ScenarioJudgement(BaseModel):
    scenario: ScenarioRequest
    action: ProposedAction
    verdict: Verdict
    explanation: VerdictExplanation
    executed: Literal[False] = Field(default=False, description="the assistant never executes anything")


class ParamSpec(BaseModel):
    type: str = "string"
    required: bool = False


class ActionSpec(BaseModel):
    """One allow-listed action type from config/action_envelope.yaml (feeds the scenario form)."""

    action_type: str
    scope: str | None = None
    blast_radius: str | None = None
    reversible: bool | None = None
    params: dict[str, ParamSpec] = Field(default_factory=dict)


class IncidentEntities(BaseModel):
    """Dropdown choices for the scenario form: entity names and candidate param values (values only)."""

    incident_id: str
    targets: list[str] = Field(
        default_factory=list, description="alert targets first, then services, pods, ..."
    )
    params: dict[str, list[str | int | float | bool]] = Field(
        default_factory=dict, description="param name -> candidate values"
    )
    other_action_types: list[str] = Field(
        default_factory=list, description="action types seen for this incident that are NOT allow-listed"
    )


class AssistantInfo(BaseModel):
    mode: Literal["llm", "offline"]
    notice: str | None = None
    default_variant: Variant = "learned"
    actions: list[ActionSpec] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    incident_id: str | None = Field(default=None, description="context: the incident on screen")
    run_id: str | None = Field(default=None, description="context: the run on screen")
    step_idx: int | None = Field(default=None, ge=0, description="context: the step on screen")


class ToolCall(BaseModel):
    tool: str
    args: dict = Field(default_factory=dict)
    ok: bool
    summary: str


class Citation(BaseModel):
    source: str = Field(description="file path, plus '#section' for markdown")
    excerpt: str


class ChatReply(BaseModel):
    answer: str
    mode: Literal["llm", "offline"]
    tool_calls: list[ToolCall] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    judgement: ScenarioJudgement | None = None
    explanation: VerdictExplanation | None = None
    notice: str | None = Field(default=None, description="e.g. why the reply fell back to offline mode")
