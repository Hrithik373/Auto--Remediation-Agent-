import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost, sseUrl } from "./client";
import type { RunRecord, StepRecord } from "./types";
import type { VerifierChoice } from "@/store/ui";

export function useRuns() {
  return useQuery({
    queryKey: ["runs"],
    queryFn: () => apiGet<RunRecord[]>("/runs"),
  });
}

export function useRun(runId: string | null | undefined) {
  return useQuery({
    queryKey: ["run", runId],
    queryFn: () => apiGet<RunRecord>(`/runs/${runId}`),
    enabled: Boolean(runId),
  });
}

interface StartRunInput {
  incident_id: string;
  verifier: VerifierChoice;
  tau: number;
  dry_run: boolean;
}

export function useStartRun() {
  return useMutation({
    mutationFn: (input: StartRunInput) => apiPost<{ run_id: string }>("/runs", input),
  });
}

export type RunStreamStatus = "idle" | "connecting" | "streaming" | "done" | "error";

interface RunStreamState {
  status: RunStreamStatus;
  steps: StepRecord[];
  final: RunRecord | null;
}

/**
 * FRONTEND_BLUEPRINT.md §5.2 / §7: the live run is an EventSource, NOT a TanStack Query -- do not
 * poll for step updates. Accumulates each `step` SSE event into local state and invalidates ["runs"]
 * once the `final` event closes the stream.
 */
export function useRunStream(runId: string | null | undefined): RunStreamState {
  const [state, setState] = useState<RunStreamState>({ status: "idle", steps: [], final: null });
  const queryClient = useQueryClient();
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    sourceRef.current?.close();
    if (!runId) {
      setState({ status: "idle", steps: [], final: null });
      return;
    }

    setState({ status: "connecting", steps: [], final: null });
    const source = new EventSource(sseUrl(`/runs/${runId}/stream`));
    sourceRef.current = source;

    source.addEventListener("open", () => {
      setState((prev) => ({ ...prev, status: "streaming" }));
    });

    source.addEventListener("step", (event) => {
      const step = JSON.parse((event as MessageEvent).data) as StepRecord;
      setState((prev) => ({ ...prev, status: "streaming", steps: [...prev.steps, step] }));
    });

    source.addEventListener("final", (event) => {
      const final = JSON.parse((event as MessageEvent).data) as RunRecord;
      setState((prev) => ({ ...prev, status: "done", final }));
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      source.close();
    });

    source.onerror = () => {
      setState((prev) => (prev.status === "done" ? prev : { ...prev, status: "error" }));
      source.close();
    };

    return () => {
      source.close();
    };
  }, [runId, queryClient]);

  return state;
}
