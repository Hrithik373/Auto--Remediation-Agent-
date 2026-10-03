import type { Decision } from "@/api/types";

/**
 * Single source of truth for "color means decision everywhere" (CLAUDE.md frontend addendum).
 * Never hardcode allow/block/revise/escalate colors outside this file -- pills, verdict bands, and
 * timeline nodes all read from here so the mapping can't drift between components.
 */

export type OutcomePill = Decision | "escalate";

export const DECISION_LABEL: Record<OutcomePill, string> = {
  allow: "Allow",
  block: "Block",
  revise: "Revise",
  escalate: "Escalate",
};

export const DECISION_CLASSES: Record<OutcomePill, { text: string; bg: string; border: string; ring: string }> = {
  allow: {
    text: "text-decision-allow",
    bg: "bg-decision-allow-soft",
    border: "border-decision-allow/40",
    ring: "ring-decision-allow/30",
  },
  block: {
    text: "text-decision-block",
    bg: "bg-decision-block-soft",
    border: "border-decision-block/40",
    ring: "ring-decision-block/30",
  },
  revise: {
    text: "text-decision-revise",
    bg: "bg-decision-revise-soft",
    border: "border-decision-revise/40",
    ring: "ring-decision-revise/30",
  },
  escalate: {
    text: "text-decision-escalate",
    bg: "bg-decision-escalate-soft",
    border: "border-decision-escalate/40",
    ring: "ring-decision-escalate/30",
  },
};

/** Step-level state machine (FRONTEND_BLUEPRINT.md §6.2): proposed -> verifying ->
 * (allowed -> executing -> resolved|failed) | blocked | revise */
export type StepState =
  | "proposed"
  | "verifying"
  | "executing"
  | "resolved"
  | "failed"
  | "blocked"
  | "revised";

export const STEP_STATE_LABEL: Record<StepState, string> = {
  proposed: "Proposed",
  verifying: "Verifying…",
  executing: "Applying…",
  resolved: "Applied · resolved",
  failed: "Applied · not resolved",
  blocked: "Blocked · never reached executor",
  revised: "Revised → retry",
};

export function outcomeForState(state: StepState): OutcomePill {
  if (state === "blocked") return "block";
  if (state === "revised") return "revise";
  return "allow";
}
