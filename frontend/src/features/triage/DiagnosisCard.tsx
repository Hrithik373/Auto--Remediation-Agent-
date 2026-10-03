import type { ProposedAction } from "@/api/types";
import Card from "@/features/shared/Card";

interface DiagnosisCardProps {
  action: ProposedAction;
}

/** The agent's root-cause read, ahead of what it's about to do about it (blueprint §3). */
export default function DiagnosisCard({ action }: DiagnosisCardProps) {
  return (
    <Card title="Diagnosis">
      <p className="text-sm leading-relaxed text-console-text">{action.rationale}</p>
      <p className="mt-2 text-2xs text-console-text-muted">
        Predicted effect: <span className="text-console-text">{action.predicted_effect}</span>
      </p>
    </Card>
  );
}
