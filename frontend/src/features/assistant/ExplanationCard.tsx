import type { GroundTruth, LayerExplanation, VerdictExplanation } from "@/api/types";
import { DECISION_CLASSES, DECISION_LABEL, type OutcomePill } from "@/lib/decisionColors";
import Card from "@/features/shared/Card";

const LAYER_LABEL: Record<LayerExplanation["verifier"], string> = {
  envelope: "Envelope",
  llm_judge: "LLM-judge",
  learned: "Learned",
};

const DECIDED_BY_LABEL: Record<VerdictExplanation["decided_by"], string> = {
  envelope: "envelope",
  llm_judge: "llm_judge",
  learned: "learned",
  none: "no layer (ungated)",
};

const ASSESSMENT_LABEL: Record<NonNullable<GroundTruth["assessment"]>, string> = {
  correct_catch: "Correct catch",
  missed: "Missed: unsafe action allowed",
  correct_allow: "Correct allow",
  false_block: "False block",
  harmless_allowed: "Allowed, harmless but ineffective",
  harmless_blocked: "Blocked, harmless either way",
  unknown: "No benchmark label",
};

function LayerLine({ layer }: { layer: LayerExplanation }) {
  const skipped = layer.decision === "skipped";
  const classes = skipped ? null : DECISION_CLASSES[layer.decision as OutcomePill];
  return (
    <li className={`flex gap-3 py-1.5 text-xs leading-relaxed ${skipped ? "opacity-40" : ""}`}>
      <span className="w-20 shrink-0 font-mono text-2xs uppercase tracking-wider text-console-text-muted">
        {LAYER_LABEL[layer.verifier]}
      </span>
      <span className="min-w-0 text-console-text">
        {classes && <span className={`mr-1.5 font-semibold ${classes.text}`}>{layer.decision}</span>}
        {layer.summary}
      </span>
    </li>
  );
}

/**
 * The assistant's plain-language reading of a verdict: who decided, by how much, and what would change
 * it. Always lists all three layers (inactive ones grayed), like VerdictCard. Built server-side by
 * assistant/explain.py, so it is deterministic and never depends on LLM wording.
 */
export default function ExplanationCard({ explanation }: { explanation: VerdictExplanation }) {
  const pill = explanation.decision as OutcomePill;
  const classes = DECISION_CLASSES[pill];
  const gt = explanation.ground_truth;

  return (
    <Card padded={false} className={`ring-1 ${classes.ring}`}>
      <div className={`flex flex-col gap-1 border-b border-console-border px-4 py-3 ${classes.bg}`}>
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-2xs font-semibold uppercase tracking-wider text-console-text-muted">Why</h3>
          <span className={`rounded px-2 py-0.5 font-mono text-2xs font-bold uppercase ${classes.text}`}>
            {DECISION_LABEL[pill]}
          </span>
        </div>
        <p className={`text-sm font-medium ${classes.text}`}>{explanation.headline}</p>
        <p className="font-mono text-2xs text-console-text-muted">
          decided by {DECIDED_BY_LABEL[explanation.decided_by]} · τ={explanation.tau.toFixed(2)}
        </p>
      </div>

      <div className="space-y-3 px-4 py-3">
        <ul className="divide-y divide-console-border/60">
          {explanation.layers.map((layer) => (
            <LayerLine key={layer.verifier} layer={layer} />
          ))}
        </ul>

        <p className="text-xs text-console-text-muted">{explanation.threshold_note}</p>

        {(explanation.counterfactuals ?? []).length > 0 && (
          <div>
            <h4 className="mb-1 text-2xs font-semibold uppercase tracking-wider text-console-text-muted">
              What would change it
            </h4>
            <ul className="space-y-1">
              {(explanation.counterfactuals ?? []).map((cf, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-console-text">
                  {cf.decision ? (
                    <span
                      className={`mt-px shrink-0 rounded px-1.5 font-mono text-2xs font-semibold ${DECISION_CLASSES[cf.decision].bg} ${DECISION_CLASSES[cf.decision].text}`}
                    >
                      {cf.decision}
                    </span>
                  ) : (
                    <span className="mt-px shrink-0 rounded bg-console-surface-2 px-1.5 font-mono text-2xs text-console-text-muted">
                      fixed
                    </span>
                  )}
                  <span className="min-w-0">{cf.description}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {gt && (
          <div className="rounded border border-console-border bg-console-surface-2 px-3 py-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h4 className="text-2xs font-semibold uppercase tracking-wider text-console-text-muted">
                Benchmark label (eval only)
              </h4>
              <span className="font-mono text-2xs text-console-text">{gt.label ?? "none"}</span>
            </div>
            <p className="mt-1 text-xs font-medium text-console-text">{ASSESSMENT_LABEL[gt.assessment ?? "unknown"]}</p>
            {gt.note && <p className="mt-0.5 text-xs text-console-text-muted">{gt.note}</p>}
          </div>
        )}
      </div>
    </Card>
  );
}
