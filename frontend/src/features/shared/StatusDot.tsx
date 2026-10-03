import type { OutcomePill } from "@/lib/decisionColors";

const DOT_CLASS: Record<OutcomePill | "critical" | "warning" | "info", string> = {
  allow: "bg-decision-allow",
  block: "bg-decision-block",
  revise: "bg-decision-revise",
  escalate: "bg-decision-escalate",
  critical: "bg-decision-block",
  warning: "bg-decision-revise",
  info: "bg-accent",
};

interface StatusDotProps {
  tone: keyof typeof DOT_CLASS;
  pulse?: boolean;
  label?: string;
}

/** Severity as a colored dot (blueprint §8) -- pair with a `label` for a live status line. */
export default function StatusDot({ tone, pulse = false, label }: StatusDotProps) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={`h-1.5 w-1.5 rounded-full ${DOT_CLASS[tone]} ${pulse ? "animate-pulse-ring" : ""}`}
        aria-hidden="true"
      />
      {label && <span className="text-2xs text-console-text-muted">{label}</span>}
    </span>
  );
}
