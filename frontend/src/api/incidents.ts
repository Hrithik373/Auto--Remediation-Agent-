// sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
// TanStack Query hooks for /api/incidents (queue) and /api/incidents/:id (detail).
// Feed the incident queue and the incident detail panes.
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";
import type { IncidentContext } from "./types";
import type { IncidentSummary } from "@/mock/fixtures";

export function useIncidents() {
  return useQuery({
    queryKey: ["incidents"],
    queryFn: () => apiGet<IncidentSummary[]>("/incidents"),
  });
}

export function useIncident(incidentId: string | null | undefined) {
  return useQuery({
    queryKey: ["incident", incidentId],
    queryFn: () => apiGet<IncidentContext>(`/incidents/${incidentId}`),
    enabled: Boolean(incidentId),
  });
}
