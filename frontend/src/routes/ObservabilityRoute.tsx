import { useEffect, useState } from "react";
import StatusDot from "@/features/shared/StatusDot";

type Reachability = "checking" | "up" | "down";

/** Grafana is cross-origin, so a no-cors probe can only tell "reachable" from "network error" --
 * which is exactly the question: is anything listening, or would the iframe be blank? */
function useGrafanaReachable(url: string | undefined): [Reachability, () => void] {
  const [state, setState] = useState<Reachability>("checking");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!url) return;
    let cancelled = false;
    setState("checking");
    fetch(new URL("/api/health", url).toString(), { mode: "no-cors", cache: "no-store" })
      .then(() => !cancelled && setState("up"))
      .catch(() => !cancelled && setState("down"));
    return () => {
      cancelled = true;
    };
  }, [url, attempt]);
  return [state, () => setAttempt((n) => n + 1)];
}

/**
 * Embedded Grafana (blueprint §0: "embed Grafana, don't rebuild it"): the provisioned "sentinel — live
 * loop" dashboard, fed by Prometheus scraping the gateway's /metrics. With the gateway running natively,
 * `make observability` (docker-compose.observability.yml) starts just Prometheus + Grafana. When Grafana
 * isn't reachable this route says so and how to start it, instead of showing a blank iframe.
 */
export default function ObservabilityRoute() {
  const grafanaUrl = import.meta.env.VITE_GRAFANA_URL as string | undefined;
  const [reachable, retry] = useGrafanaReachable(grafanaUrl);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-console-text">Observability</h1>
          <p className="mt-1 text-sm text-console-text-muted">
            Live verifier activity from the gateway&rsquo;s <code className="font-mono text-console-text">/metrics</code>:
            verdicts by decision and layer, run outcomes, step latency and LLM spend.
          </p>
        </div>
        {grafanaUrl && reachable === "up" && (
          <a
            href={grafanaUrl.replace(/[?&]kiosk\b/, "")}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-accent hover:underline"
          >
            Open in Grafana &rarr;
          </a>
        )}
      </div>

      {!grafanaUrl ? (
        <Notice>
          Grafana isn&rsquo;t part of this deployment (no <code className="font-mono">VITE_GRAFANA_URL</code>). Raw
          counters are at <code className="font-mono">/metrics</code>; locally, <code className="font-mono">npm run dev:live</code>{" "}
          plus <code className="font-mono">make observability</code> shows the dashboard here.
        </Notice>
      ) : reachable === "up" ? (
        <iframe title="Grafana" src={grafanaUrl} className="mt-6 h-[75vh] w-full rounded-lg border border-console-border" />
      ) : (
        <Notice>
          {reachable === "checking" ? (
            <StatusDot tone="info" pulse label="Looking for Grafana…" />
          ) : (
            <div className="space-y-2 text-center">
              <p>
                Grafana isn&rsquo;t reachable at <code className="font-mono text-console-text">{new URL(grafanaUrl).origin}</code>.
              </p>
              <p>
                Start Prometheus + Grafana (needs Docker Desktop running):{" "}
                <code className="font-mono text-console-text">make observability</code>
              </p>
              <button onClick={retry} className="text-xs text-accent hover:underline">
                Check again
              </button>
            </div>
          )}
        </Notice>
      )}
    </div>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-6 flex min-h-64 items-center justify-center rounded-lg border border-dashed border-console-border px-6 py-10 text-sm text-console-text-muted">
      {children}
    </div>
  );
}
