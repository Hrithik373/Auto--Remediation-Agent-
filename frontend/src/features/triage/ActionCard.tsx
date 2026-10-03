import type { ProposedAction } from "@/api/types";
import Card from "@/features/shared/Card";
import Tag from "@/features/shared/Tag";
import CodeBlock from "@/features/shared/CodeBlock";

interface ActionCardProps {
  action: ProposedAction;
  collapsed?: boolean;
}

/** A ProposedAction rendered (blueprint §3). Untrusted until the VerdictCard clears it. */
export default function ActionCard({ action, collapsed = false }: ActionCardProps) {
  return (
    <Card title="Proposed action">
      <div className="flex flex-wrap items-center gap-2">
        <Tag tone="accent">{action.action_type}</Tag>
        <span className="text-console-text-muted">&rarr;</span>
        <span className="font-mono text-sm text-console-text">{action.target}</span>
      </div>
      {!collapsed && Object.keys(action.params ?? {}).length > 0 && (
        <div className="mt-3">
          <CodeBlock value={action.params} maxHeight="8rem" />
        </div>
      )}
    </Card>
  );
}
