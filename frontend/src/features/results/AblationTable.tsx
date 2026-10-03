import type { AblationRow } from "@/mock/fixtures";
import { formatPct } from "@/lib/format";
import Card from "@/features/shared/Card";

interface AblationTableProps {
  rows: AblationRow[];
}

// Rates are fractions -> percent; counts like steps_to_mitigation are plain numbers.
function formatValue(metric: string, value: number | null): string {
  if (value == null) return "—";
  return metric.startsWith("steps") ? value.toFixed(2) : formatPct(value);
}

/** Verifier on/off, layers, block handling, agent quality, topology features (eval/ablations.py). */
export default function AblationTable({ rows }: AblationTableProps) {
  const groups = new Map<string, AblationRow[]>();
  for (const row of rows) {
    if (!groups.has(row.name)) groups.set(row.name, []);
    groups.get(row.name)!.push(row);
  }

  return (
    <Card title="Ablations" padded={false}>
      <div className="divide-y divide-console-border">
        {[...groups.entries()].map(([name, group]) => (
          <div key={name} className="px-4 py-3">
            <h4 className="mb-2 text-2xs font-semibold uppercase tracking-wider text-console-text-muted">{name}</h4>
            <div className="space-y-1.5">
              {group.map((row) => (
                <div key={`${row.variant}|${row.metric}`} className="flex items-center justify-between gap-4 text-sm">
                  <span className="font-mono text-console-text">{row.variant}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-2xs text-console-text-muted">{row.metric}</span>
                    <span className="w-14 text-right font-mono font-semibold text-console-text [font-variant-numeric:tabular-nums]">
                      {formatValue(row.metric, row.value)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
