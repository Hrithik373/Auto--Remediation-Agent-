import type {
  ActionSpec,
  AssistantInfo,
  ChatReply,
  ChatRequest,
  IncidentContext,
  IncidentEntities,
  LayerVerdict,
  ScenarioJudgement,
  ScenarioRequest,
  Verdict,
  VerdictExplanation,
} from "@/api/types";

/**
 * Mock-mode stand-ins for /api/assistant/* so the Assistant route renders with no backend. These are
 * CANNED: a tiny rule (allow-list check + a fixed risk per action type) shaped like the real payloads.
 * Real verdicts and explanations come from src/sentinel/assistant/ on the gateway. Every reply says so.
 */

const MOCK_NOTICE = "Mock mode (MSW): canned replies. Start the gateway for real verifier verdicts.";

export const MOCK_ACTIONS: ActionSpec[] = [
  { action_type: "restart_pod", blast_radius: "low", reversible: true, params: { namespace: { type: "string", required: true }, pod_name: { type: "string", required: true } } },
  { action_type: "restart_service", blast_radius: "low", reversible: true, params: { namespace: { type: "string", required: true }, service: { type: "string", required: true } } },
  { action_type: "rollback_deployment", blast_radius: "medium", reversible: true, params: { namespace: { type: "string", required: true }, deployment: { type: "string", required: true }, revision: { type: "integer", required: false } } },
  { action_type: "scale_deployment", blast_radius: "medium", reversible: true, params: { namespace: { type: "string", required: true }, deployment: { type: "string", required: true }, replicas: { type: "integer", required: true } } },
  { action_type: "cordon_node", blast_radius: "medium", reversible: true, params: { node_name: { type: "string", required: true } } },
  { action_type: "toggle_feature_flag", blast_radius: "low", reversible: true, params: { namespace: { type: "string", required: true }, configmap: { type: "string", required: true }, flag: { type: "string", required: true }, enabled: { type: "boolean", required: true } } },
];

/** Canned learned-layer risk per action type: high for capacity-removing actions. */
const MOCK_RISK: Record<string, number> = { cordon_node: 0.86, scale_deployment: 0.71 };

export const MOCK_INFO: AssistantInfo = {
  mode: "offline",
  notice: MOCK_NOTICE,
  default_variant: "learned",
  actions: MOCK_ACTIONS,
};

function skipped(verifier: LayerVerdict["verifier"], reason: string): LayerVerdict {
  return { verifier, decision: "skipped", reasons: [reason] };
}

function mockVerdict(req: ScenarioRequest): Verdict {
  const tau = req.tau ?? 0.5;
  if (!MOCK_ACTIONS.some((a) => a.action_type === req.action_type)) {
    const reason = `action_type '${req.action_type}' is not in the allow-list (action_envelope.yaml)`;
    return {
      decision: "block", risk_score: 1, verifier: "combined", reasons: [reason],
      layers: [
        { verifier: "envelope", decision: "block", risk_score: 1, reasons: [reason] },
        skipped("llm_judge", "layer not active for this run"),
        skipped("learned", "not evaluated: the envelope already blocked"),
      ],
    };
  }
  const risk = MOCK_RISK[req.action_type] ?? 0.08;
  const over = risk >= tau;
  return {
    decision: over ? "block" : "allow", risk_score: risk, verifier: "combined",
    reasons: [`risk ${risk.toFixed(2)} (learned) is ${over ? "at or above" : "below"} tau=${tau.toFixed(2)}`],
    layers: [
      { verifier: "envelope", decision: "allow", risk_score: 0.2, reasons: [`action_type '${req.action_type}' is allow-listed`, "params satisfy schema"] },
      skipped("llm_judge", "layer not active for this run"),
      { verifier: "learned", decision: over ? "block" : "allow", risk_score: risk, reasons: [`P(destructive) = ${risk.toFixed(2)} (mock)`] },
    ],
  };
}

export function mockExplanation(verdict: Verdict, tau: number): VerdictExplanation {
  const layers = verdict.layers ?? [];
  const env = layers.find((l) => l.verifier === "envelope");
  const envBlocked = env?.decision === "block";
  const scored = layers.filter((l) => l.verifier !== "envelope" && l.decision !== "skipped");
  const top = scored.sort((a, b) => (b.risk_score ?? 0) - (a.risk_score ?? 0))[0];
  const decidedBy = envBlocked ? "envelope" : (top?.verifier ?? "envelope");
  const r = verdict.risk_score;
  const headline = envBlocked
    ? `BLOCKED by the envelope: ${env?.reasons?.[0] ?? "envelope rule"}.`
    : verdict.decision === "allow"
      ? `ALLOWED: the highest risk, ${r.toFixed(2)} from the ${decidedBy}, is below τ=${tau.toFixed(2)}.`
      : `${verdict.decision === "revise" ? "SENT BACK FOR REVISION" : "BLOCKED"}: the ${decidedBy} scored risk ${r.toFixed(2)}, at or above τ=${tau.toFixed(2)}.`;
  return {
    decision: verdict.decision,
    decided_by: decidedBy,
    headline,
    tau,
    threshold_note: envBlocked
      ? "τ does not matter here: the envelope is a hard gate checked before any risk score."
      : `Risk ${r.toFixed(2)} vs τ=${tau.toFixed(2)} (mock).`,
    layers: (["envelope", "llm_judge", "learned"] as const).map((name) => {
      const l = layers.find((x) => x.verifier === name) ?? skipped(name, "layer not active for this run");
      return {
        verifier: name,
        decision: l.decision,
        risk_score: l.risk_score ?? null,
        summary: l.decision === "skipped" ? `The ${name} layer did not run.` : `${name}: ${l.decision}${l.risk_score != null ? ` (risk ${l.risk_score.toFixed(2)})` : ""}.`,
        reasons: l.reasons ?? [],
      };
    }),
    counterfactuals: envBlocked
      ? [{ kind: "threshold", description: "No value of τ can allow this action; only changing the action itself can." }]
      : verdict.decision === "allow"
        ? [{ kind: "threshold", description: `Lowering τ to ${r.toFixed(2)} or below would stop this action.`, decision: "block" }]
        : [{ kind: "threshold", description: `Raising τ above ${r.toFixed(2)} would let this action through.`, decision: "allow" }],
    ground_truth: { label: null, provenance: "mock", assessment: "unknown", note: "Mock mode has no benchmark labels." },
  };
}

export function mockScenario(req: ScenarioRequest): ScenarioJudgement {
  const verdict = mockVerdict(req);
  return {
    scenario: req,
    action: {
      action_type: req.action_type, target: req.target, params: req.params ?? {},
      rationale: `Telemetry points at '${req.target}'; proposing ${req.action_type} to mitigate the symptoms.`,
      predicted_effect: `${req.action_type} on '${req.target}' should clear the active alerts.`,
    },
    verdict,
    explanation: mockExplanation(verdict, req.tau ?? 0.5),
    executed: false,
  };
}

export function mockChat(req: ChatRequest): ChatReply {
  const text = req.messages[req.messages.length - 1].content.toLowerCase();
  const action = [...MOCK_ACTIONS.map((a) => a.action_type), "drain_node", "delete_namespace"].find((a) =>
    text.replace(/[\s-]+/g, "_").includes(a),
  );
  const target = /\b(?:on|to|of)\s+([a-z0-9][\w.-]*)/.exec(text)?.[1];
  if (action && target) {
    const judgement = mockScenario({ incident_id: req.incident_id ?? "pod-crashloop", action_type: action, target, params: {}, tau: 0.5 });
    return {
      answer: `Mock judgement for ${action} on ${target}:\n\n${judgement.explanation.headline}`,
      mode: "offline", notice: MOCK_NOTICE, judgement, explanation: judgement.explanation,
      tool_calls: [{ tool: "evaluate_scenario", args: { action_type: action, target }, ok: true, summary: `${action} on ${target} -> ${judgement.verdict.decision} (mock)` }],
      citations: [],
    };
  }
  return {
    answer:
      "The verifier has three layers. The envelope is a deterministic allow-list (action type, params, blast radius); " +
      "it blocks first and no τ can override it. Then the LLM judge and/or the learned XGBoost model score the risk, and " +
      "the policy allows the action only if the highest risk is below τ.\n\n(This is a canned mock answer.)",
    mode: "offline", notice: MOCK_NOTICE,
    tool_calls: [{ tool: "search_docs", args: { query: text }, ok: true, summary: "1 doc snippet(s): ARCHITECTURE_BLUEPRINT.md (mock)" }],
    citations: [{ source: "ARCHITECTURE_BLUEPRINT.md#6-the-verification-layer", excerpt: "final = envelope_pass AND (score < threshold τ)" }],
  };
}

/** Mock dropdown choices: services and alert targets from the mock incident's telemetry, plus
 * generic values. The real endpoint also mines the incident's candidate actions. */
export function mockEntities(incident: IncidentContext | undefined, incidentId: string): IncidentEntities {
  const services = ((incident?.telemetry.topology as { services?: string[] } | undefined)?.services ?? []).filter(
    (s): s is string => typeof s === "string",
  );
  const alertTargets = (incident?.telemetry.alerts ?? []).map((a) => String((a as { target?: unknown }).target ?? "")).filter(Boolean);
  const targets = [...new Set([...alertTargets, ...services])];
  return {
    incident_id: incidentId,
    targets,
    params: {
      namespace: ["prod"],
      service: targets,
      deployment: targets,
      pod_name: alertTargets,
      node_name: ["node-17", "node-22"],
      replicas: [0, 1, 2, 3, 5],
      revision: [41],
      enabled: [false, true],
    },
    other_action_types: ["delete_namespace", "drain_node"],
  };
}
