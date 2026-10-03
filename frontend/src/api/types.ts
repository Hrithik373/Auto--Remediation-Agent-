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
