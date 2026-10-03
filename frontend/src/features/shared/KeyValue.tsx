import type { ReactNode } from "react";

interface KeyValueProps {
  label: string;
  value: ReactNode;
  mono?: boolean;
}

export default function KeyValue({ label, value, mono = false }: KeyValueProps) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1 text-sm">
      <span className="text-console-text-muted">{label}</span>
      <span className={mono ? "font-mono text-console-text" : "text-console-text"}>{value}</span>
    </div>
  );
}
