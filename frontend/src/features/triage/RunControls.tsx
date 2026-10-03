import { useUiStore, type VerifierChoice } from "@/store/ui";
import { useStartRun } from "@/api/runs";
import Card from "@/features/shared/Card";

const VERIFIER_OPTIONS: { value: VerifierChoice; label: string; title: string }[] = [
  { value: "none", label: "Ungated", title: "No verification -- the baseline that shows what the verifier prevents" },
  { value: "envelope", label: "Envelope only", title: "Deterministic allow-list gate" },
  { value: "learned", label: "Learned", title: "Envelope + learned verifier (runs offline)" },
  { value: "llm_judge", label: "LLM-judge", title: "Envelope + LLM judge (needs Anthropic credentials on the gateway)" },
  { value: "combined", label: "Combined", title: "Envelope + judge + learned (needs Anthropic credentials)" },
];

interface RunControlsProps {
  incidentId: string;
  onStarted: (runId: string) => void;
  disabled?: boolean;
}

/** Start run, pick verifier, τ slider, dry-run toggle (blueprint §6.2 demo step 3). Driving the τ
 * slider live is the "trade-off knob" moment -- it stays synced with ParetoChart via the ui store. */
export default function RunControls({ incidentId, onStarted, disabled }: RunControlsProps) {
  const { tau, verifierChoice, dryRun, setTau, setVerifierChoice, setDryRun } = useUiStore();
  const startRun = useStartRun();

  const handleStart = () => {
    startRun.mutate(
      { incident_id: incidentId, verifier: verifierChoice, tau, dry_run: dryRun },
      { onSuccess: (data) => onStarted(data.run_id) },
    );
  };

  return (
    <Card title="Run controls">
      <div className="flex flex-col gap-4">
        <div>
          <label className="mb-1.5 block text-2xs uppercase tracking-wider text-console-text-muted">Verifier</label>
          <div className="flex flex-wrap gap-1">
            {VERIFIER_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                title={opt.title}
                onClick={() => setVerifierChoice(opt.value)}
                className={`rounded border px-2.5 py-1 text-xs transition-colors ${
                  verifierChoice === opt.value
                    ? "border-accent/50 bg-accent-soft text-accent"
                    : "border-console-border text-console-text-muted hover:text-console-text"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="mb-1.5 flex items-center justify-between text-2xs uppercase tracking-wider text-console-text-muted">
            <span>Risk threshold τ</span>
            <span className="font-mono text-console-text">{tau.toFixed(2)}</span>
          </label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={tau}
            onChange={(e) => setTau(Number(e.target.value))}
            className="w-full accent-accent"
          />
        </div>

        <label className="flex items-center gap-2 text-xs text-console-text-muted">
          <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} className="accent-accent" />
          Dry-run (never reaches real apply)
        </label>

        <button
          onClick={handleStart}
          disabled={disabled || startRun.isPending}
          className="rounded bg-accent px-3 py-2 text-sm font-semibold text-console-bg transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {startRun.isPending ? "Starting…" : "Start run"}
        </button>
      </div>
    </Card>
  );
}
