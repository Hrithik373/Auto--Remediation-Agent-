import type { ReactNode } from "react";

interface TagProps {
  children: ReactNode;
  mono?: boolean;
  tone?: "neutral" | "accent";
}

/** Fault-family and action-type tags render mono per blueprint §8 -- anything a machine emitted. */
export default function Tag({ children, mono = true, tone = "neutral" }: TagProps) {
  const toneClasses =
    tone === "accent"
      ? "border-accent/40 bg-accent-soft text-accent"
      : "border-console-border bg-console-surface-2 text-console-text-muted";
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-2xs ${
        mono ? "font-mono" : "font-sans"
      } ${toneClasses}`}
    >
      {children}
    </span>
  );
}
