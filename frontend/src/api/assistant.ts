// sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
// Hooks for /api/assistant/* (Phase P6): bot info, chat, what-if scenario judgements, step explanations.
// Chat and scenarios are mutations (each call is a new question); explanations are cached queries.
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiGet, apiPost } from "./client";
import type {
  AssistantInfo,
  ChatReply,
  ChatRequest,
  IncidentEntities,
  ScenarioJudgement,
  ScenarioRequest,
  VerdictExplanation,
} from "./types";

export function useAssistantInfo() {
  return useQuery({
    queryKey: ["assistant-info"],
    queryFn: () => apiGet<AssistantInfo>("/assistant/info"),
    staleTime: 60_000,
  });
}

/** Dropdown choices for the scenario form: the incident's entities and candidate param values. */
export function useIncidentEntities(incidentId: string | null | undefined) {
  return useQuery({
    queryKey: ["assistant-entities", incidentId],
    queryFn: () => apiGet<IncidentEntities>(`/assistant/entities/${incidentId}`),
    enabled: Boolean(incidentId),
    staleTime: 5 * 60_000,
  });
}

export function useAssistantChat() {
  return useMutation({
    mutationFn: (body: ChatRequest) => apiPost<ChatReply>("/assistant/chat", body),
  });
}

export function useScenario() {
  return useMutation({
    mutationFn: (body: ScenarioRequest) => apiPost<ScenarioJudgement>("/assistant/scenario", body),
  });
}

export function useStepExplanation(runId: string | null | undefined, stepIdx: number | null | undefined) {
  return useQuery({
    queryKey: ["explain", runId, stepIdx],
    queryFn: () => apiGet<VerdictExplanation>(`/assistant/explain/${runId}/${stepIdx}`),
    enabled: Boolean(runId) && stepIdx != null,
  });
}
