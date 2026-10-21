/**
 * GENERATED FILE -- do not hand-edit.
 * Source: src/sentinel/schemas/*.py (Pydantic v2)
 * Regenerate: `npm run types` (frontend/) or `make types` (repo root).
 */

export type Logs = string[];
/**
 * span records
 */
export type Traces = {
  [k: string]: unknown;
}[];
export type Alerts = {
  [k: string]: unknown;
}[];
export type IncidentId = string;
export type Source = "aiopslab" | "itbench" | "offline";
/**
 * Ground-truth fault family. For eval/labeling only — never fed to the agent's prompt, or the diagnosis task becomes trivial.
 */
export type FaultFamily = string | null;
/**
 * Context compaction target (context/builder.py, Phase P1)
 */
export type BudgetTokens = number;
export type ActionType = string;
/**
 * service / pod / namespace / resource
 */
export type Target = string;
/**
 * agent's justification
 */
export type Rationale = string;
/**
 * what the agent thinks will happen
 */
export type PredictedEffect = string;
export type Executed = boolean;
export type DryRun = boolean;
/**
 * from env oracle; None if not executed
 */
export type Resolved = boolean | null;
export type SideEffects = string[];
export type Error = string | null;
export type Decision = "allow" | "block" | "revise";
export type RiskScore = number;
/**
 * One reason per entry, human-readable — these render directly in the triage console (Phase P5). See CLAUDE.md style rules.
 */
export type Reasons = string[];
export type Verifier = "envelope" | "llm_judge" | "learned" | "combined";
export type Verifier1 = "envelope" | "llm_judge" | "learned";
/**
 * 'skipped' means this layer wasn't active for the run's verifier config -- the console grays it out rather than omitting it (blueprint §6.1: 'the viewer should see which layers were in play').
 */
export type Decision1 = "allow" | "block" | "revise" | "skipped";
export type RiskScore1 = number | null;
export type Reasons1 = string[];
/**
 * Per-layer breakdown when verifier='combined' (Phase P2 policy.py). Empty for a single-layer verdict (e.g. envelope alone in Phase P0/P1).
 */
export type Layers = LayerVerdict[];
export type StepIdx = number;
export type Tokens = number;
export type LatencyMs = number;
/**
 * Eval-only label (labeling/oracle_labeler.py), attached by the orchestrator AFTER the verdict is final -- never visible to the agent or any verifier. eval/metrics.py reads it for bad-action-prevented and false-block rates. None = no label derivable (needs human review).
 */
export type GroundTruthLabel = ("correct" | "ineffective" | "destructive" | "out_of_envelope") | null;
export type IncidentId1 = string;
export type Seed = number;
/**
 * hash of the resolved run config
 */
export type ConfigHash = string;
export type Steps = StepRecord[];
export type FinalResolved = boolean;
/**
 * The key safety metric: did any destructive-labeled action ever reach executor.run(dry_run=False)?
 */
export type UnsafeActionReachedExec = boolean;
/**
 * mean time-to-mitigation
 */
export type MttmMs = number | null;
export type TotalTokens = number;
export type TotalCostUsd = number;
export type IncidentId2 = string;
export type ActionType1 = string;
export type Target1 = string;
/**
 * optional; a neutral template is used when empty
 */
export type Rationale1 = string;
export type Variant = "none" | "envelope" | "llm_judge" | "learned" | "combined";
export type Tau = number;
/**
 * also re-verify under the offline variants (none, envelope, learned)
 */
export type CompareVariants = boolean;
export type Decision2 = "allow" | "block" | "revise";
export type DecidedBy = "envelope" | "llm_judge" | "learned" | "none";
export type Headline = string;
export type Verifier2 = "envelope" | "llm_judge" | "learned";
export type Decision3 = "allow" | "block" | "revise" | "skipped";
export type RiskScore2 = number | null;
/**
 * secondary layers only: risk_score >= tau. None for envelope/skipped.
 */
export type OverThreshold = boolean | null;
/**
 * one plain-language sentence
 */
export type Summary = string;
export type Reasons2 = string[];
export type Layers1 = LayerExplanation[];
export type Tau1 = number;
export type ThresholdNote = string;
export type Kind = "threshold" | "variant";
export type Description = string;
/**
 * the decision under this alternative
 */
export type Decision4 = ("allow" | "block" | "revise") | null;
export type Counterfactuals = Counterfactual[];
export type Label = ("correct" | "ineffective" | "destructive" | "out_of_envelope") | null;
export type Provenance = string;
export type Assessment =
  "correct_catch" | "missed" | "correct_allow" | "false_block" | "harmless_allowed" | "harmless_blocked" | "unknown";
export type Note = string;
/**
 * the assistant never executes anything
 */
export type Executed1 = false;
/**
 * @minItems 1
 */
export type Messages = [ChatMessage, ...ChatMessage[]];
export type Role = "user" | "assistant";
export type Content = string;
/**
 * context: the incident on screen
 */
export type IncidentId3 = string | null;
/**
 * context: the run on screen
 */
export type RunId = string | null;
/**
 * context: the step on screen
 */
export type StepIdx1 = number | null;
export type Answer = string;
export type Mode = "llm" | "offline";
export type Tool = string;
export type Ok = boolean;
export type Summary1 = string;
export type ToolCalls = ToolCall[];
/**
 * file path, plus '#section' for markdown
 */
export type Source1 = string;
export type Excerpt = string;
export type Citations = Citation[];
/**
 * e.g. why the reply fell back to offline mode
 */
export type Notice = string | null;
export type Mode1 = "llm" | "offline";
export type Notice1 = string | null;
export type DefaultVariant = "none" | "envelope" | "llm_judge" | "learned" | "combined";
export type ActionType2 = string;
export type Scope = string | null;
export type BlastRadius = string | null;
export type Reversible = boolean | null;
export type Type = string;
export type Required = boolean;
export type Actions = ActionSpec[];
export type IncidentId4 = string;
/**
 * alert targets first, then services, pods, ...
 */
export type Targets = string[];
/**
 * action types seen for this incident that are NOT allow-listed
 */
export type OtherActionTypes = string[];

export interface SentinelSchemas {}
/**
 * Raw observability signal for one incident, as pulled from the env adapter.
 *
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "Telemetry".
 */
export interface Telemetry {
  logs?: Logs;
  metrics?: Metrics;
  traces?: Traces;
  topology?: Topology;
  alerts?: Alerts;
}
/**
 * metric_name -> series
 */
export interface Metrics {
  [k: string]: number[];
}
/**
 * service dependency graph
 */
export interface Topology {
  [k: string]: unknown;
}
/**
 * Everything the diagnosis agent (Phase P1) is given for one incident.
 *
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "IncidentContext".
 */
export interface IncidentContext {
  incident_id: IncidentId;
  source: Source;
  fault_family?: FaultFamily;
  telemetry: Telemetry;
  budget_tokens: BudgetTokens;
}
/**
 * A single remediation action proposed by the diagnosis agent. Untrusted until verified.
 *
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "ProposedAction".
 */
export interface ProposedAction {
  action_type: ActionType;
  target: Target;
  params?: Params;
  rationale: Rationale;
  predicted_effect: PredictedEffect;
}
export interface Params {
  [k: string]: unknown;
}
/**
 * Outcome of handing a ProposedAction to executor.run() (Phase P1).
 *
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "ExecutionResult".
 */
export interface ExecutionResult {
  executed: Executed;
  dry_run: DryRun;
  resolved?: Resolved;
  side_effects?: SideEffects;
  error?: Error;
}
/**
 * A verifier's ruling on one ProposedAction.
 *
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "Verdict".
 */
export interface Verdict {
  decision: Decision;
  risk_score: RiskScore;
  reasons?: Reasons;
  verifier: Verifier;
  layers?: Layers;
}
/**
 * One verification layer's sub-ruling within a combined Verdict.
 *
 * Added for FRONTEND_BLUEPRINT.md §6.1's VerdictCard, which must render the decision pipeline
 * ("envelope passed, judge blocked, why") rather than a single collapsed decision — the layered
 * view is the project's contribution and CLAUDE.md's frontend addendum requires it stay visible.
 * `verifier/policy.py`'s CombinedPolicy (Phase P2) populates `Verdict.layers` with one entry per
 * active layer; a single-layer verdict (e.g. EnvelopeVerifier alone) leaves `layers` empty.
 *
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "LayerVerdict".
 */
export interface LayerVerdict {
  verifier: Verifier1;
  decision: Decision1;
  risk_score?: RiskScore1;
  reasons?: Reasons1;
}
/**
 * One iteration of the orchestrator loop (propose -> verify -> act/revise/escalate).
 *
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "StepRecord".
 */
export interface StepRecord {
  step_idx: StepIdx;
  proposed: ProposedAction;
  verdict: Verdict;
  result?: ExecutionResult | null;
  tokens: Tokens;
  latency_ms: LatencyMs;
  ground_truth_label?: GroundTruthLabel;
}
/**
 * One full incident run: incident_id x seed x config, reproducible via config_hash.
 *
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "RunRecord".
 */
export interface RunRecord {
  incident_id: IncidentId1;
  seed: Seed;
  config_hash: ConfigHash;
  steps?: Steps;
  final_resolved: FinalResolved;
  unsafe_action_reached_exec: UnsafeActionReachedExec;
  mttm_ms?: MttmMs;
  total_tokens?: TotalTokens;
  total_cost_usd?: TotalCostUsd;
}
/**
 * 'What would the verifier say if the agent proposed THIS on THAT incident?'
 *
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "ScenarioRequest".
 */
export interface ScenarioRequest {
  incident_id: IncidentId2;
  action_type: ActionType1;
  target: Target1;
  params?: Params1;
  rationale?: Rationale1;
  variant?: Variant;
  tau?: Tau;
  compare_variants?: CompareVariants;
}
export interface Params1 {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "ScenarioJudgement".
 */
export interface ScenarioJudgement {
  scenario: ScenarioRequest;
  action: ProposedAction;
  verdict: Verdict;
  explanation: VerdictExplanation;
  executed?: Executed1;
}
/**
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "VerdictExplanation".
 */
export interface VerdictExplanation {
  decision: Decision2;
  decided_by: DecidedBy;
  headline: Headline;
  layers: Layers1;
  tau: Tau1;
  threshold_note: ThresholdNote;
  counterfactuals?: Counterfactuals;
  ground_truth?: GroundTruth | null;
}
/**
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "LayerExplanation".
 */
export interface LayerExplanation {
  verifier: Verifier2;
  decision: Decision3;
  risk_score?: RiskScore2;
  over_threshold?: OverThreshold;
  summary: Summary;
  reasons?: Reasons2;
}
/**
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "Counterfactual".
 */
export interface Counterfactual {
  kind: Kind;
  description: Description;
  decision?: Decision4;
}
/**
 * The oracle label for this action (eval-only ground truth) and what it says about the verdict.
 *
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "GroundTruth".
 */
export interface GroundTruth {
  label?: Label;
  provenance?: Provenance;
  assessment?: Assessment;
  note?: Note;
}
/**
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "ChatRequest".
 */
export interface ChatRequest {
  messages: Messages;
  incident_id?: IncidentId3;
  run_id?: RunId;
  step_idx?: StepIdx1;
}
/**
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "ChatMessage".
 */
export interface ChatMessage {
  role: Role;
  content: Content;
}
/**
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "ChatReply".
 */
export interface ChatReply {
  answer: Answer;
  mode: Mode;
  tool_calls?: ToolCalls;
  citations?: Citations;
  judgement?: ScenarioJudgement | null;
  explanation?: VerdictExplanation | null;
  notice?: Notice;
}
/**
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "ToolCall".
 */
export interface ToolCall {
  tool: Tool;
  args?: Args;
  ok: Ok;
  summary: Summary1;
}
export interface Args {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "Citation".
 */
export interface Citation {
  source: Source1;
  excerpt: Excerpt;
}
/**
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "AssistantInfo".
 */
export interface AssistantInfo {
  mode: Mode1;
  notice?: Notice1;
  default_variant?: DefaultVariant;
  actions?: Actions;
}
/**
 * One allow-listed action type from config/action_envelope.yaml (feeds the scenario form).
 *
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "ActionSpec".
 */
export interface ActionSpec {
  action_type: ActionType2;
  scope?: Scope;
  blast_radius?: BlastRadius;
  reversible?: Reversible;
  params?: Params2;
}
export interface Params2 {
  [k: string]: ParamSpec;
}
/**
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "ParamSpec".
 */
export interface ParamSpec {
  type?: Type;
  required?: Required;
}
/**
 * Dropdown choices for the scenario form: entity names and candidate param values (values only).
 *
 * This interface was referenced by `SentinelSchemas`'s JSON-Schema
 * via the `definition` "IncidentEntities".
 */
export interface IncidentEntities {
  incident_id: IncidentId4;
  targets?: Targets;
  params?: Params3;
  other_action_types?: OtherActionTypes;
}
/**
 * param name -> candidate values
 */
export interface Params3 {
  [k: string]: (string | number | boolean)[];
}
