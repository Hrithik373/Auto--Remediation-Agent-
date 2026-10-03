import { usePareto, useMetrics, usePreventionPartition, useAblations } from "@/api/experiments";
import ParetoChart from "@/features/results/ParetoChart";
import MetricsGrid from "@/features/results/MetricsGrid";
import PreventionPartition from "@/features/results/PreventionPartition";
import AblationTable from "@/features/results/AblationTable";
import { EXPERIMENTS_SOURCE } from "@/mock/fixtures";

const MOCK_MODE = import.meta.env.VITE_USE_MOCKS !== "false";

/** Where the aggregate numbers live (blueprint §4). Live: /api/experiments/* rebuilds them from the
 * DuckDB rows `make eval` wrote. Mock mode: a measured snapshot of that same output. */
export default function ResultsRoute() {
  const pareto = usePareto();
  const metrics = useMetrics();
  const prevention = usePreventionPartition();
  const ablations = useAblations();
  const empty = metrics.data !== undefined && metrics.data.length === 0;

  return (
    <div className="mx-auto max-w-5xl space-y-4 px-6 py-8">
      <div>
        <h1 className="text-lg font-semibold text-console-text">Results</h1>
        <p className="mt-1 text-sm text-console-text-muted">
          Risk&ndash;autonomy Pareto, baseline metrics, and the prevention partition by verification layer.
        </p>
        <p className="mt-1 font-mono text-2xs text-console-text-muted">
          {MOCK_MODE ? `mock mode: ${EXPERIMENTS_SOURCE}` : "live: rebuilt from the gateway's DuckDB run store"}
        </p>
      </div>

      {empty ? (
        <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-console-border text-sm text-console-text-muted">
          No evaluation results in the store yet &mdash; run <code className="mx-1 font-mono">make eval</code>.
        </div>
      ) : (
        <>
          {pareto.data && <ParetoChart series={pareto.data} />}
          {prevention.data && <PreventionPartition rows={prevention.data} />}
          <div className="grid gap-4 lg:grid-cols-2">
            {metrics.data && <MetricsGrid rows={metrics.data} />}
            {ablations.data && <AblationTable rows={ablations.data} />}
          </div>
        </>
      )}
    </div>
  );
}
