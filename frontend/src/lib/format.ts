/** Formatting helpers for anything a machine emitted (durations, tokens, cost, risk). */

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  return `${m}m ${rem}s`;
}

export function formatTokens(tokens: number | null | undefined): string {
  if (tokens == null) return "—";
  if (tokens < 1000) return `${tokens}`;
  return `${(tokens / 1000).toFixed(1)}k`;
}

export function formatUsd(usd: number | null | undefined): string {
  if (usd == null) return "—";
  return `$${usd.toFixed(usd < 1 ? 4 : 2)}`;
}

export function formatRiskPct(riskScore: number | null | undefined): string {
  if (riskScore == null) return "—";
  return `${Math.round(riskScore * 100)}%`;
}

export function formatPct(fraction: number | null | undefined): string {
  if (fraction == null) return "—";
  return `${(fraction * 100).toFixed(1)}%`;
}

export function formatTimestamp(iso: string | number | Date): string {
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, { hour12: false });
}
