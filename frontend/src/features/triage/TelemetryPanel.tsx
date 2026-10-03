import { useState } from "react";
import type { Telemetry } from "@/api/types";
import Card from "@/features/shared/Card";
import CodeBlock from "@/features/shared/CodeBlock";

type Tab = "logs" | "metrics" | "traces" | "alerts";
const TABS: { key: Tab; label: string }[] = [
  { key: "logs", label: "Logs" },
  { key: "metrics", label: "Metrics" },
  { key: "traces", label: "Traces" },
  { key: "alerts", label: "Alerts" },
];

interface TelemetryPanelProps {
  telemetry: Telemetry;
}

/** The evidence panel (blueprint §4 demo script step 2): "here's what the on-call engineer would see." */
export default function TelemetryPanel({ telemetry }: TelemetryPanelProps) {
  const [tab, setTab] = useState<Tab>("logs");
  // Telemetry's fields default to [] / {} at the Pydantic layer (schemas/incident.py) but JSON Schema
  // marks default_factory fields optional, so the generated types carry `?` -- normalize once here.
  const logs = telemetry.logs ?? [];
  const metrics = telemetry.metrics ?? {};
  const traces = telemetry.traces ?? [];
  const alerts = telemetry.alerts ?? [];

  return (
    <Card
      padded={false}
      title={
        <div className="flex gap-1">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`rounded px-2.5 py-1 text-2xs font-semibold uppercase tracking-wider transition-colors ${
                tab === t.key
                  ? "bg-accent-soft text-accent"
                  : "text-console-text-muted hover:text-console-text"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      }
    >
      <div className="p-4">
        {tab === "logs" && (
          <div className="max-h-64 space-y-1 overflow-auto font-mono text-2xs leading-relaxed">
            {logs.length === 0 && <p className="text-console-text-muted">No log lines.</p>}
            {logs.map((line, i) => (
              <div key={i} className="border-b border-console-border/60 py-1 text-console-text-muted last:border-b-0">
                <span className={line.includes("FATAL") || line.includes("ERROR") ? "text-decision-block" : ""}>
                  {line}
                </span>
              </div>
            ))}
          </div>
        )}
        {tab === "metrics" && (
          <div className="space-y-3">
            {Object.entries(metrics).length === 0 && (
              <p className="text-sm text-console-text-muted">No metrics.</p>
            )}
            {Object.entries(metrics).map(([name, series]) => (
              <div key={name}>
                <div className="mb-1 font-mono text-2xs text-console-text-muted">{name}</div>
                <div className="flex items-end gap-0.5" style={{ height: "40px" }}>
                  {series.map((v, i) => {
                    const max = Math.max(...series, 1);
                    return (
                      <div
                        key={i}
                        className="flex-1 rounded-t bg-accent/60"
                        style={{ height: `${Math.max((v / max) * 100, 4)}%` }}
                        title={String(v)}
                      />
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
        {tab === "traces" && <CodeBlock value={traces} />}
        {tab === "alerts" && <CodeBlock value={alerts} />}
      </div>
    </Card>
  );
}
