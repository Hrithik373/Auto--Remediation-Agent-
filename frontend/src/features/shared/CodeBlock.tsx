interface CodeBlockProps {
  value: unknown;
  maxHeight?: string;
}

/** Renders params/telemetry JSON in monospace with its own horizontal scroll (never the page). */
export default function CodeBlock({ value, maxHeight = "16rem" }: CodeBlockProps) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return (
    <pre
      className="overflow-auto rounded border border-console-border bg-console-bg p-3 font-mono text-2xs leading-relaxed text-console-text-muted"
      style={{ maxHeight }}
    >
      {text}
    </pre>
  );
}
