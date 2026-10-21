import { create } from "zustand";
import type { ChatReply } from "@/api/types";

/** One exchange in the chat: the user's question and, once it arrives, the assistant's reply. */
export interface ChatTurn {
  id: number;
  question: string;
  reply: ChatReply | null;
  error: string | null;
}

/** What the user is looking at, sent with each question so "why was this blocked?" just works. */
export interface AssistantContextRef {
  incidentId: string | null;
  runId: string | null;
  stepIdx: number | null;
}

interface AssistantState {
  turns: ChatTurn[];
  context: AssistantContextRef;
  pendingQuestion: string | null;
  addTurn: (question: string) => number;
  resolveTurn: (id: number, reply: ChatReply) => void;
  failTurn: (id: number, error: string) => void;
  setContext: (context: Partial<AssistantContextRef>) => void;
  clearContext: () => void;
  /** Triage's "Ask why" sets this; the chat panel sends it once and clears it. */
  askLater: (question: string, context: Partial<AssistantContextRef>) => void;
  takePendingQuestion: () => string | null;
  reset: () => void;
}

const EMPTY_CONTEXT: AssistantContextRef = { incidentId: null, runId: null, stepIdx: null };
let nextId = 1;

/**
 * Chat history and context for the Assistant route. Session-only UI state in Zustand (no
 * localStorage, per the frontend conventions); the server keeps no chat history either.
 */
export const useAssistantStore = create<AssistantState>((set, get) => ({
  turns: [],
  context: EMPTY_CONTEXT,
  pendingQuestion: null,
  addTurn: (question) => {
    const id = nextId++;
    set((s) => ({ turns: [...s.turns, { id, question, reply: null, error: null }] }));
    return id;
  },
  resolveTurn: (id, reply) => set((s) => ({ turns: s.turns.map((t) => (t.id === id ? { ...t, reply } : t)) })),
  failTurn: (id, error) => set((s) => ({ turns: s.turns.map((t) => (t.id === id ? { ...t, error } : t)) })),
  setContext: (context) => set((s) => ({ context: { ...s.context, ...context } })),
  clearContext: () => set({ context: EMPTY_CONTEXT }),
  askLater: (question, context) => set({ pendingQuestion: question, context: { ...EMPTY_CONTEXT, ...context } }),
  takePendingQuestion: () => {
    const question = get().pendingQuestion;
    if (question) set({ pendingQuestion: null });
    return question;
  },
  reset: () => set({ turns: [], context: EMPTY_CONTEXT, pendingQuestion: null }),
}));
