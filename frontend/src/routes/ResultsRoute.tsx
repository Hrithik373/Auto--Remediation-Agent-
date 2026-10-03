import { usePareto, useMetrics, usePreventionPartition, useAblations } from "@/api/experiments";
import ParetoChart from "@/features/results/ParetoChart";
import MetricsGrid from "@/features/results/MetricsGrid";
import PreventionPartition from "@/features/results/PreventionPartition";
import AblationTable from "@/features/results/AblationTable";

/** Where the aggregate numbers live (blueprint §4). Reads finished RunRecords from DuckDB via
 * /api/experiments/* once Phase P4 exists; mock mode serves the same shape from fixtures. */
export default function ResultsRoute() {
  const pareto = usePareto();
  const metrics = useMetrics();
  const prevention = usePreventionPartition();
  const ablations = useAblations();

  return (
    <div className="mx-auto max-w-5xl space-y-4 px-6 py-8">
      <div>
        <h1 className="text-lg font-semibold text-console-text">Results</h1>
        <p className="mt-1 text-sm text-console-text-muted">
          Risk&ndash;autonomy Pareto, baseline metrics, and the envelope-vs-judge prevention partition.
        </p>
      </div>

      {pareto.data && <ParetoChart series={pareto.data} />}
      {prevention.data && <PreventionPartition rows={prevention.data} />}
      <div className="grid gap-4 lg:grid-cols-2">
        {metrics.data && <MetricsGrid rows={metrics.data} />}
        {ablations.data && <AblationTable rows={ablations.data} />}
      </div>
    </div>
  );
}
