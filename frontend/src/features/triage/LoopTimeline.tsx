import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { RunRecord, StepRecord } from "@/api/types";
import type { RunStreamStatus } from "@/api/runs";
import { DECISION_CLASSES, type OutcomePill } from "@/lib/decisionColors";
import { formatDuration, formatTokens, formatUsd } from "@/lib/format";
import ActionCard from "./ActionCard";
import VerdictCard from "./VerdictCard";
import StatusDot from "@/features/shared/StatusDot";
import { useAssistantStore } from "@/store/assistant";

function outcomePillForStep(step: StepRecord): { pill: OutcomePill; label: string } {
  if (step.verdict.decision === "block") return { pill: "block", label: "blocked" };
  if (step.verdict.decision === "revise") return { pill: "revise", label: "revised → retry" };
  if (step.result?.resolved) return { pill: "allow", label: "applied · resolved" };
  return { pill: "allow", label: "applied · not resolved" };
}

interface StepNodeProps {
  step: StepRecord;
  tau: number;
  index: number;
  runId?: string | null;
  incidentId?: string;
}

function StepNode({ step, tau, index, runId, incidentId }: StepNodeProps) {
  const [expanded, setExpanded] = useState(index === 0 || step.verdict.decision !== "allow");
  const navigate = useNavigate();
  const askLater = useAssistantStore((s) => s.askLater);
  const askWhy = () => {
    const verb = step.verdict.decision === "allow" ? "allowed" : step.verdict.decision === "revise" ? "sent back" : "blocked";
    askLater(`Why was step ${step.step_idx} (${step.proposed.action_type} on ${step.proposed.target}) ${verb}?`, {
      incidentId: incidentId ?? null,
      runId: runId ?? null,
      stepIdx: step.step_idx,
    });
    navigate("/assistant");
  };
  const { pill, label } = outcomePillForStep(step);
  const classes = DECISION_CLASSES[pill];

  return (
    <div className="relative pl-8">
      <span className={`absolute left-0 top-1 h-3 w-3 rounded-full border-2 border-console-bg ${classes.bg} ring-2 ${classes.ring}`} />
      {index > 0 && <span className="absolute -top-4 left-[5px] h-4 w-px bg-console-border" />}

      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between gap-3 rounded px-2 py-1.5 text-left transition-colors hover:bg-console-surface-2"
      >
        <div className="flex items-center gap-2 text-sm">
          <span className="font-mono text-2xs text-console-text-muted">step {step.step_idx}</span>
          <span className="font-mono text-console-text">{step.proposed.action_type}</span>
          <span className="text-console-text-muted">&rarr;</span>
          <span className="font-mono text-console-text-muted">{step.proposed.target}</span>
        </div>
        <span className={`rounded px-2 py-0.5 text-2xs font-semibold ${classes.bg} ${classes.text}`}>{label}</span>
      </button>

      {expanded && (
        <div className="mt-2 grid gap-3 pb-4 pl-2 sm:grid-cols-2">
          <ActionCard action={step.proposed} />
          <div className="space-y-2">
            <VerdictCard verdict={step.verdict} tau={tau} />
            {runId && (
              <button onClick={askWhy} className="text-2xs text-accent hover:underline">
                Ask why &rarr;
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function RunSummary({ run }: { run: RunRecord }) {
  return (
    <div className="relative mt-1 pl-8">
      <span
        className={`absolute left-0 top-1 h-3 w-3 rounded-full border-2 border-console-bg ${
          run.final_resolved ? "bg-decision-allow" : "bg-decision-block"
        }`}
      />
      <span className="absolute -top-4 left-[5px] h-4 w-px bg-console-border" />
      <div className="rounded-lg border border-console-border bg-console-surface-2 p-4">
        <div className="mb-2 flex items-center gap-2">
          <StatusDot tone={run.final_resolved ? "allow" : "block"} />
          <span className="text-sm font-semibold text-console-text">
            {run.final_resolved ? "Resolved" : "Not resolved"}
          </span>
        </div>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-4">
          <div>
            <dt className="text-console-text-muted">Unsafe action reached exec</dt>
            <dd className={`font-mono font-semibold ${run.unsafe_action_reached_exec ? "text-decision-block" : "text-decision-allow"}`}>
              {run.unsafe_action_reached_exec ? "yes" : "no"}
            </dd>
          </div>
          <div>
            <dt className="text-console-text-muted">MTTM</dt>
            <dd className="font-mono text-console-text">{formatDuration(run.mttm_ms)}</dd>
          </div>
          <div>
            <dt className="text-console-text-muted">Tokens</dt>
            <dd className="font-mono text-console-text">{formatTokens(run.total_tokens)}</dd>
          </div>
          <div>
            <dt className="text-console-text-muted">Cost</dt>
            <dd className="font-mono text-console-text">{formatUsd(run.total_cost_usd)}</dd>
          </div>
        </dl>
      </div>
    </div>
  );
}

interface LoopTimelineProps {
  steps: StepRecord[];
  status: RunStreamStatus;
  final: RunRecord | null;
  tau: number;
  /** When set, each step offers "Ask why", which opens the Assistant with this run as context. */
  runId?: string | null;
  incidentId?: string;
}

/** ★ The live trace (blueprint §6.2). Streams in via SSE; each node is one orchestrator step. */
export default function LoopTimeline({ steps, status, final, tau, runId, incidentId }: LoopTimelineProps) {
  if (status === "idle") {
    return <p className="text-sm text-console-text-muted">Start a run to see the loop trace.</p>;
  }

  return (
    <div className="space-y-4">
      {steps.map((step, i) => (
        <div key={step.step_idx} className="animate-fade-in">
          <StepNode step={step} tau={tau} index={i} runId={runId} incidentId={incidentId} />
        </div>
      ))}

      {(status === "connecting" || status === "streaming") && (
        <div className="relative pl-8">
          <span className="absolute left-0 top-1 h-3 w-3 rounded-full bg-accent animate-pulse-ring" />
          {steps.length > 0 && <span className="absolute -top-4 left-[5px] h-4 w-px bg-console-border" />}
          <span className="pl-2 text-xs text-console-text-muted">
            {status === "connecting" ? "connecting…" : "diagnosing next step…"}
          </span>
        </div>
      )}

      {status === "error" && (
        <p className="pl-8 text-xs text-decision-block">Stream error — the run may still have progressed server-side.</p>
      )}

      {status === "done" && final && <RunSummary run={final} />}
    </div>
  );
}
