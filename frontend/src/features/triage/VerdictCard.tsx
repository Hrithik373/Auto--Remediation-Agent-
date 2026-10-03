import type { LayerVerdict, Verdict } from "@/api/types";
import { DECISION_CLASSES, DECISION_LABEL, type OutcomePill } from "@/lib/decisionColors";
import { formatRiskPct } from "@/lib/format";
import Card from "@/features/shared/Card";

const LAYER_LABEL: Record<LayerVerdict["verifier"], string> = {
  envelope: "Envelope",
  llm_judge: "LLM-judge",
  learned: "Learned",
};

function LayerRow({ layer, tau }: { layer: LayerVerdict; tau: number }) {
  const skipped = layer.decision === "skipped";
  const pill = (skipped ? "allow" : layer.decision) as OutcomePill;
  const classes = DECISION_CLASSES[pill];

  return (
    <div className={`flex flex-col gap-1 border-b border-console-border/70 py-2.5 last:border-b-0 ${skipped ? "opacity-40" : ""}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="w-24 shrink-0 font-mono text-2xs uppercase tracking-wider text-console-text-muted">
          {LAYER_LABEL[layer.verifier]}
        </span>
        {skipped ? (
          <span className="text-2xs text-console-text-muted">not active for this run</span>
        ) : (
          <span className={`flex items-center gap-1.5 text-xs font-semibold ${classes.text}`}>
            {layer.decision === "allow" ? "✔" : layer.decision === "block" ? "✘" : "⟲"}
            {DECISION_LABEL[layer.decision as Exclude<LayerVerdict["decision"], "skipped">]}
            {layer.risk_score != null && (
              <span className="font-mono font-normal text-console-text-muted">
                risk {formatRiskPct(layer.risk_score)}
                {layer.verifier !== "envelope" && ` (τ=${tau})`}
              </span>
            )}
          </span>
        )}
      </div>
      {!skipped &&
        (layer.reasons ?? []).map((reason, i) => (
          <p key={i} className="ml-24 pl-3 text-xs leading-relaxed text-console-text-muted">
            └ {reason}
          </p>
        ))}
    </div>
  );
}

interface VerdictCardProps {
  verdict: Verdict;
  tau: number;
}

/**
 * ★ The money component (blueprint §6.1). Renders a Verdict as a decision pipeline, not a single
 * collapsed decision -- the panel must see that the envelope passed something and the judge caught
 * it. Never render just `verdict.decision`; always show every layer, graying out inactive ones.
 */
export default function VerdictCard({ verdict, tau }: VerdictCardProps) {
  const finalPill = verdict.decision as OutcomePill;
  const finalClasses = DECISION_CLASSES[finalPill];
  const layers = verdict.layers ?? [];

  return (
    <Card padded={false} className={`ring-1 ${finalClasses.ring}`}>
      <div className="flex items-center justify-between border-b border-console-border px-4 py-2.5">
        <h3 className="text-2xs font-semibold uppercase tracking-wider text-console-text-muted">Verdict</h3>
        <span className={`rounded px-2 py-0.5 font-mono text-2xs font-bold uppercase ${finalClasses.bg} ${finalClasses.text}`}>
          {verdict.decision}
        </span>
      </div>

      <div className="px-4">
        {layers.length > 0 ? (
          layers.map((layer) => <LayerRow key={layer.verifier} layer={layer} tau={tau} />)
        ) : (
          <div className="py-2.5 text-xs text-console-text-muted">
            Single-layer verdict from <span className="font-mono">{verdict.verifier}</span>.
          </div>
        )}
      </div>

      <div className={`flex items-center justify-between px-4 py-2.5 text-xs ${finalClasses.bg}`}>
        <span className={`font-semibold ${finalClasses.text}`}>
          COMBINED · {DECISION_LABEL[finalPill]}
        </span>
        <span className="text-console-text-muted">
          {verdict.decision === "allow"
            ? "cleared for execution"
            : verdict.decision === "block"
              ? "never reached executor"
              : "returned to agent for revision"}
        </span>
      </div>
    </Card>
  );
}
