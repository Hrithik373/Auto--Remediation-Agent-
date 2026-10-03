import { useIncidents } from "@/api/incidents";
import IncidentTable from "@/features/queue/IncidentTable";

export default function QueueRoute() {
  const { data: incidents, isLoading, isError } = useIncidents();

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-console-text">Incident queue</h1>
        <p className="mt-1 text-sm text-console-text-muted">
          Real fault-injected snapshots from the offline benchmark fixtures. Select one to open triage.
        </p>
      </div>

      {isLoading && <p className="text-sm text-console-text-muted">Loading incidents…</p>}
      {isError && <p className="text-sm text-decision-block">Could not load incidents.</p>}
      {incidents && <IncidentTable incidents={incidents} />}
    </div>
  );
}
