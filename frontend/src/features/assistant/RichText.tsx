import type { ReactNode } from "react";

/** Inline **bold** and `code` -> React nodes. Never injects HTML: model text stays plain text. */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={i} className="font-semibold text-console-text">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code key={i} className="rounded bg-console-surface-2 px-1 font-mono text-[0.85em]">
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
}

/**
 * The assistant's answer text. LLMs answer in light markdown, so this renders exactly three things:
 * paragraphs, "- " bullet lists (one nesting level) and inline bold/code. Everything else is text.
 */
export default function RichText({ text }: { text: string }) {
  const blocks = text.split(/\n\s*\n/);
  return (
    <div className="space-y-2 text-sm leading-relaxed text-console-text">
      {blocks.map((block, b) => {
        const lines = block.split("\n");
        if (lines.every((l) => /^\s*[-*]\s+/.test(l))) {
          return (
            <ul key={b} className="space-y-1">
              {lines.map((l, i) => {
                const nested = /^\s{2,}/.test(l);
                return (
                  <li key={i} className={`flex gap-2 ${nested ? "ml-5" : ""}`}>
                    <span className="text-console-text-muted" aria-hidden="true">
                      {nested ? "◦" : "•"}
                    </span>
                    <span className="min-w-0">{inline(l.replace(/^\s*[-*]\s+/, ""))}</span>
                  </li>
                );
              })}
            </ul>
          );
        }
        return (
          <p key={b} className="whitespace-pre-wrap">
            {inline(block)}
          </p>
        );
      })}
    </div>
  );
}
