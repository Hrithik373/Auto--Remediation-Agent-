import type { HTMLAttributes, ReactNode } from "react";

interface CardProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  title?: ReactNode;
  action?: ReactNode;
  padded?: boolean;
}

export default function Card({ title, action, padded = true, className = "", children, ...rest }: CardProps) {
  return (
    <div
      className={`rounded-lg border border-console-border bg-console-surface ${className}`}
      {...rest}
    >
      {(title || action) && (
        <div className="flex items-center justify-between border-b border-console-border px-4 py-2.5">
          {typeof title === "string" ? (
            <h3 className="text-2xs font-semibold uppercase tracking-wider text-console-text-muted">
              {title}
            </h3>
          ) : (
            title
          )}
          {action}
        </div>
      )}
      <div className={padded ? "p-4" : ""}>{children}</div>
    </div>
  );
}
