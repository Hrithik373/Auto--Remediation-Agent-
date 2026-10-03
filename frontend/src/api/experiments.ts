import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";
import type { AblationRow, MetricsRow, ParetoPoint, PreventionRow } from "@/mock/fixtures";

export function usePareto(verifier?: string) {
  return useQuery({
    queryKey: ["pareto", verifier ?? "all"],
    queryFn: () =>
      apiGet<Record<string, ParetoPoint[]>>(`/experiments/pareto${verifier ? `?verifier=${verifier}` : ""}`),
  });
}

export function useMetrics() {
  return useQuery({
    queryKey: ["metrics"],
    queryFn: () => apiGet<MetricsRow[]>("/experiments/metrics"),
  });
}

export function usePreventionPartition() {
  return useQuery({
    queryKey: ["prevention-partition"],
    queryFn: () => apiGet<PreventionRow[]>("/experiments/prevention_partition"),
  });
}

export function useAblations() {
  return useQuery({
    queryKey: ["ablations"],
    queryFn: () => apiGet<AblationRow[]>("/experiments/ablations"),
  });
}
