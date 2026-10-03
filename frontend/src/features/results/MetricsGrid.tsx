import type { MetricsRow } from "@/mock/fixtures";
import { formatDuration, formatPct, formatUsd } from "@/lib/format";
import Card from "@/features/shared/Card";

interface MetricsGridProps {
  rows: MetricsRow[];
}

/** resolution / bad-prevented / false-block / MTTM / cost per baseline (blueprint §6.3). Plain
 * magnitude comparison across baselines -- a table, not a chart (dataviz skill's form heuristic). */
export default function MetricsGrid({ rows }: MetricsGridProps) {
  return (
    <Card title="Baseline metrics" padded={false}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[600px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-console-border text-left text-2xs uppercase tracking-wider text-console-text-muted">
              <th className="px-4 py-2 font-medium">Baseline</th>
              <th className="px-4 py-2 text-right font-medium">Resolution</th>
              <th className="px-4 py-2 text-right font-medium">Bad-prevented</th>
              <th className="px-4 py-2 text-right font-medium">False-block</th>
              <th className="px-4 py-2 text-right font-medium">MTTM</th>
              <th className="px-4 py-2 text-right font-medium">Cost / incident</th>
            </tr>
          </thead>
          <tbody className="[font-variant-numeric:tabular-nums]">
            {rows.map((row) => (
              <tr key={row.baseline} className="border-b border-console-border last:border-b-0">
                <td className="px-4 py-2.5 text-console-text">{row.baseline}</td>
                <td className="px-4 py-2.5 text-right font-mono text-console-text">{formatPct(row.resolution)}</td>
                <td className="px-4 py-2.5 text-right font-mono text-console-text">{formatPct(row.bad_prevented)}</td>
                <td className="px-4 py-2.5 text-right font-mono text-console-text">{formatPct(row.false_block)}</td>
                <td className="px-4 py-2.5 text-right font-mono text-console-text-muted">{formatDuration(row.mttm_ms)}</td>
                <td className="px-4 py-2.5 text-right font-mono text-console-text-muted">{formatUsd(row.cost_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
