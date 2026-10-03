import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useIncident } from "@/api/incidents";
import { useRunStream } from "@/api/runs";
import { useUiStore } from "@/store/ui";
import TelemetryPanel from "@/features/triage/TelemetryPanel";
import TopologyGraph from "@/features/triage/TopologyGraph";
import DiagnosisCard from "@/features/triage/DiagnosisCard";
import RunControls from "@/features/triage/RunControls";
import LoopTimeline from "@/features/triage/LoopTimeline";
import Card from "@/features/shared/Card";

/** The hero screen (blueprint §1, §4): diagnose → propose → verify → act, live. */
export default function TriageRoute() {
  const { incidentId } = useParams<{ incidentId: string }>();
  const { data: incident, isLoading, isError } = useIncident(incidentId);
  const [runId, setRunId] = useState<string | null>(null);
  const tau = useUiStore((s) => s.tau);
  const stream = useRunStream(runId);

  if (isLoading) return <div className="p-8 text-sm text-console-text-muted">Loading incident…</div>;
  if (isError || !incident) {
    return (
      <div className="p-8 text-sm text-decision-block">
        Could not load incident.{" "}
        <Link to="/" className="text-accent underline">
          Back to queue
        </Link>
      </div>
    );
  }

  const latestAction = stream.steps.at(-1)?.proposed;

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <Link to="/" className="text-2xs text-console-text-muted hover:text-console-text">
            ← Queue
          </Link>
          <h1 className="mt-1 font-mono text-lg font-semibold text-console-text">{incident.incident_id}</h1>
          <p className="text-sm text-console-text-muted">
            {incident.source} · {incident.fault_family}
          </p>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_1fr_320px]">
        <div className="space-y-4 lg:col-span-2">
          <div className="grid gap-4 sm:grid-cols-2">
            <TelemetryPanel telemetry={incident.telemetry} />
            <TopologyGraph telemetry={incident.telemetry} />
          </div>

          {latestAction && <DiagnosisCard action={latestAction} />}

          <Card title="Loop trace">
            <LoopTimeline steps={stream.steps} status={stream.status} final={stream.final} tau={tau} />
          </Card>
        </div>

        <div>
          <RunControls
            incidentId={incident.incident_id}
            onStarted={setRunId}
            disabled={stream.status === "connecting" || stream.status === "streaming"}
          />
        </div>
      </div>
    </div>
  );
}
