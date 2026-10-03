import { useNavigate } from "react-router-dom";
import type { IncidentSummary } from "@/mock/fixtures";
import Tag from "@/features/shared/Tag";
import StatusDot from "@/features/shared/StatusDot";

const STATUS_TONE: Record<IncidentSummary["status"], "allow" | "block" | "revise" | "escalate"> = {
  resolved: "allow",
  blocked: "block",
  queued: "revise",
  escalated: "escalate",
};

const STATUS_LABEL: Record<IncidentSummary["status"], string> = {
  resolved: "Resolved",
  blocked: "Blocked",
  queued: "Queued",
  escalated: "Escalated",
};

interface IncidentTableProps {
  incidents: IncidentSummary[];
}

/** Screen 1 (blueprint §1): proves incidents are real benchmark snapshots, not toy data. */
export default function IncidentTable({ incidents }: IncidentTableProps) {
  const navigate = useNavigate();

  return (
    <div className="overflow-x-auto rounded-lg border border-console-border">
      <table className="w-full min-w-[640px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-console-border bg-console-surface-2 text-left text-2xs uppercase tracking-wider text-console-text-muted">
            <th className="px-4 py-2.5 font-medium">Incident</th>
            <th className="px-4 py-2.5 font-medium">Source</th>
            <th className="px-4 py-2.5 font-medium">Fault family</th>
            <th className="px-4 py-2.5 font-medium">Alerts</th>
            <th className="px-4 py-2.5 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {incidents.map((incident) => (
            <tr
              key={incident.incident_id}
              onClick={() => navigate(`/incidents/${incident.incident_id}`)}
              className="cursor-pointer border-b border-console-border bg-console-surface transition-colors last:border-b-0 hover:bg-console-surface-2"
            >
              <td className="px-4 py-3 font-mono text-console-text">{incident.incident_id}</td>
              <td className="px-4 py-3">
                <Tag>{incident.source}</Tag>
              </td>
              <td className="px-4 py-3">
                <Tag tone="accent">{incident.fault_family}</Tag>
              </td>
              <td className="px-4 py-3 font-mono text-console-text-muted">{incident.n_alerts}</td>
              <td className="px-4 py-3">
                <StatusDot tone={STATUS_TONE[incident.status]} label={STATUS_LABEL[incident.status]} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
