/**
 * Embedded Grafana (blueprint §0: "embed Grafana, don't rebuild it"). Points at the docker-compose
 * `grafana` service (Phase P5e) once it exists -- not up in mock mode, so this route explains that
 * rather than showing a broken iframe.
 */
export default function ObservabilityRoute() {
  const grafanaUrl = import.meta.env.VITE_GRAFANA_URL as string | undefined;

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <h1 className="text-lg font-semibold text-console-text">Observability</h1>
      <p className="mt-1 text-sm text-console-text-muted">
        System instrumentation and reproducibility (blueprint §1). Embeds Grafana from
        docker-compose.yml's <code className="font-mono text-console-text">grafana</code> service.
      </p>

      {grafanaUrl ? (
        <iframe title="Grafana" src={grafanaUrl} className="mt-6 h-[70vh] w-full rounded-lg border border-console-border" />
      ) : (
        <div className="mt-6 flex h-64 items-center justify-center rounded-lg border border-dashed border-console-border text-sm text-console-text-muted">
          Grafana isn&rsquo;t running yet (Phase P5e). Set <code className="font-mono">VITE_GRAFANA_URL</code> once{" "}
          <code className="font-mono">make demo</code> brings the stack up.
        </div>
      )}
    </div>
  );
}
