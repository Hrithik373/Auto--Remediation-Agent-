import { create } from "zustand";
import type { Verdict } from "@/api/types";

type VerifierChoice = Verdict["verifier"];

interface UiState {
  selectedIncidentId: string | null;
  tau: number;
  verifierChoice: VerifierChoice;
  dryRun: boolean;
  setSelectedIncidentId: (id: string | null) => void;
  setTau: (tau: number) => void;
  setVerifierChoice: (choice: VerifierChoice) => void;
  setDryRun: (dryRun: boolean) => void;
}

/**
 * The little cross-component UI state (FRONTEND_BLUEPRINT.md §7): selectedIncidentId, tau,
 * verifierChoice, dryRun. Drives both RunControls and ParetoChart's tau marker so the two stay in
 * sync. No localStorage (CLAUDE.md frontend addendum) -- this is session-only UI state, not
 * something that needs to survive a reload.
 */
export const useUiStore = create<UiState>((set) => ({
  selectedIncidentId: null,
  tau: 0.5,
  verifierChoice: "combined",
  dryRun: true,
  setSelectedIncidentId: (id) => set({ selectedIncidentId: id }),
  setTau: (tau) => set({ tau }),
  setVerifierChoice: (choice) => set({ verifierChoice: choice }),
  setDryRun: (dryRun) => set({ dryRun }),
}));
