import { useEffect, useRef, useState } from "react";
import type { ChatMessage, ChatReply, ChatRequest } from "@/api/types";
import { useAssistantChat } from "@/api/assistant";
import { useAssistantStore, type ChatTurn } from "@/store/assistant";
import Card from "@/features/shared/Card";
import VerdictCard from "@/features/triage/VerdictCard";
import ActionCard from "@/features/triage/ActionCard";
import ExplanationCard from "./ExplanationCard";
import RichText from "./RichText";

const SUGGESTIONS = [
  "Would drain_node on node-17 be allowed for bad-rollout-latency?",
  "Would restart_service on cart be allowed for itbench-sre-scenario-2?",
  "How does the envelope decide?",
  "What are the evaluation results?",
  "How does the learned verifier avoid leaking incidents?",
];

function ToolTrace({ reply }: { reply: ChatReply }) {
  const calls = reply.tool_calls ?? [];
  const citations = reply.citations ?? [];
  if (calls.length === 0 && citations.length === 0) return null;
  return (
    <details className="text-2xs text-console-text-muted">
      <summary className="cursor-pointer select-none hover:text-console-text">
        {calls.length} tool call{calls.length === 1 ? "" : "s"}
        {citations.length > 0 && ` · ${citations.length} source${citations.length === 1 ? "" : "s"}`}
      </summary>
      <ul className="mt-1.5 space-y-1 border-l border-console-border pl-3">
        {calls.map((call, i) => (
          <li key={i} className="font-mono">
            <span className={call.ok ? "text-console-text" : "text-console-text-muted line-through"}>{call.tool}</span>
            {" · "}
            {call.summary}
          </li>
        ))}
        {citations.map((c, i) => (
          <li key={`c${i}`} className="font-mono">
            source · {c.source}
          </li>
        ))}
      </ul>
    </details>
  );
}

function AssistantReply({ reply }: { reply: ChatReply }) {
  const judgement = reply.judgement;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded border border-console-border bg-console-surface-2 px-1.5 py-0.5 font-mono text-2xs text-console-text-muted">
          {reply.mode === "llm" ? "LLM + tools" : "offline mode"}
        </span>
        {reply.notice && <span className="text-2xs text-console-text-muted">{reply.notice}</span>}
      </div>
      <RichText text={reply.answer} />
      {judgement && (
        <div className="grid gap-3 xl:grid-cols-2">
          <div className="space-y-3">
            <ActionCard action={judgement.action} />
            <VerdictCard verdict={judgement.verdict} tau={judgement.scenario.tau ?? 0.5} />
          </div>
          <ExplanationCard explanation={judgement.explanation} />
        </div>
      )}
      {!judgement && reply.explanation && <ExplanationCard explanation={reply.explanation} />}
      <ToolTrace reply={reply} />
    </div>
  );
}

function Turn({ turn }: { turn: ChatTurn }) {
  return (
    <div className="space-y-3">
      <div className="ml-auto max-w-[85%] rounded-lg bg-accent-soft px-3 py-2 text-sm text-console-text">
        {turn.question}
      </div>
      {turn.reply ? (
        <AssistantReply reply={turn.reply} />
      ) : turn.error ? (
        <p className="text-sm text-decision-block">Could not reach the assistant: {turn.error}</p>
      ) : (
        <p className="animate-pulse text-sm text-console-text-muted">Checking with the verifier…</p>
      )}
    </div>
  );
}

/** Conversation with the explainer bot. Judgements always come back as the real policy's Verdict,
 * rendered with VerdictCard (every layer visible) next to the plain-language explanation. */
export default function ChatPanel() {
  const { turns, context, addTurn, resolveTurn, failTurn, clearContext, takePendingQuestion } = useAssistantStore();
  const chat = useAssistantChat();
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  const ask = (question: string) => {
    const text = question.trim();
    if (!text || chat.isPending) return;
    const id = addTurn(text);
    // Prior completed turns give the LLM the conversation; the server keeps no history.
    const history: ChatMessage[] = turns.flatMap((t) =>
      t.reply ? [{ role: "user", content: t.question }, { role: "assistant", content: t.reply.answer }] : [],
    );
    const current: ChatMessage = { role: "user", content: text };
    const recent = history.slice(-8);
    const messages: ChatRequest["messages"] = recent.length ? [recent[0], ...recent.slice(1), current] : [current];
    // mutateAsync's promise, not mutate()'s callbacks: those are dropped if this panel unmounts
    // mid-request (StrictMode remounts it right after "Ask why" auto-sends), leaving the turn stuck.
    chat
      .mutateAsync({ messages, incident_id: context.incidentId, run_id: context.runId, step_idx: context.stepIdx })
      .then((reply) => resolveTurn(id, reply))
      .catch((err: unknown) => failTurn(id, err instanceof Error ? err.message : String(err)));
    setDraft("");
  };

  useEffect(() => {
    const pending = takePendingQuestion();
    if (pending) ask(pending);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once when arriving from "Ask why"
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const hasContext = context.incidentId || context.runId;

  return (
    <Card title="Ask Sentinel" padded={false} className="flex min-h-[32rem] flex-col">
      <div className="flex-1 space-y-6 overflow-y-auto px-4 py-4" aria-live="polite">
        {turns.length === 0 ? (
          <div className="space-y-3">
            <p className="text-sm text-console-text-muted">
              Ask how any part of the system works, or whether an action would be allowed. Verdicts come from the
              real verifier policy; the assistant only explains them and can't execute anything.
            </p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => ask(s)}
                  className="rounded border border-console-border bg-console-surface-2 px-2.5 py-1 text-left text-xs text-console-text-muted transition-colors hover:border-accent/50 hover:text-console-text"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          turns.map((turn) => <Turn key={turn.id} turn={turn} />)
        )}
        <div ref={endRef} />
      </div>

      <form
        className="space-y-2 border-t border-console-border p-3"
        onSubmit={(e) => {
          e.preventDefault();
          ask(draft);
        }}
      >
        {hasContext && (
          <div className="flex items-center justify-between gap-2 font-mono text-2xs text-console-text-muted">
            <span>
              context: {context.incidentId ?? "—"}
              {context.runId && ` · run ${context.runId}`}
              {context.stepIdx != null && ` · step ${context.stepIdx}`}
            </span>
            <button type="button" onClick={clearContext} className="hover:text-console-text">
              clear
            </button>
          </div>
        )}
        <div className="flex gap-2">
          <label htmlFor="assistant-question" className="sr-only">
            Question
          </label>
          <textarea
            id="assistant-question"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                ask(draft);
              }
            }}
            rows={2}
            placeholder="e.g. why was step 0 blocked?  ·  would cordon_node on node-17 be allowed for bad-rollout-latency?"
            className="min-w-0 flex-1 resize-none rounded border border-console-border bg-console-bg px-3 py-2 text-sm text-console-text placeholder:text-console-text-muted/60 focus:border-accent focus:outline-none"
          />
          <button
            type="submit"
            disabled={chat.isPending || !draft.trim()}
            className="self-end rounded bg-accent px-4 py-2 text-sm font-semibold text-console-bg transition-opacity disabled:opacity-40"
          >
            Ask
          </button>
        </div>
      </form>
    </Card>
  );
}
