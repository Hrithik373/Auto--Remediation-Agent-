import { useAssistantInfo } from "@/api/assistant";
import StatusDot from "@/features/shared/StatusDot";
import ChatPanel from "@/features/assistant/ChatPanel";
import ScenarioPanel from "@/features/assistant/ScenarioPanel";

/** Phase P6 (ASSISTANT_BLUEPRINT.md): the explainer bot. Chat on the left, an exact what-if form on
 * the right. Both read verdicts from the real verifier policy; neither can execute anything. */
export default function AssistantRoute() {
  const info = useAssistantInfo();
  const mode = info.data?.mode;

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-console-text">Assistant</h1>
          <p className="mt-1 max-w-2xl text-sm text-console-text-muted">
            Explains how sentinel works and why the verifier allows, revises or blocks an action. It never decides
            and never executes. Every verdict shown here comes from the verifier policy.
          </p>
        </div>
        {mode && (
          <div className="flex flex-col items-end gap-0.5" data-testid="assistant-mode">
            <StatusDot tone={mode === "llm" ? "allow" : "info"} label={mode === "llm" ? "LLM + tools" : "offline mode"} />
            {info.data?.notice && <span className="max-w-xs text-right text-2xs text-console-text-muted">{info.data.notice}</span>}
          </div>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_400px]">
        <div className="min-w-0">
          <ChatPanel />
        </div>
        <div className="min-w-0">
          <ScenarioPanel />
        </div>
      </div>
    </div>
  );
}
