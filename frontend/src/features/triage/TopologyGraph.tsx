import { useMemo } from "react";
import ReactFlow, { Background, Controls, type Edge, type Node, Position } from "reactflow";
import "reactflow/dist/style.css";
import type { Telemetry } from "@/api/types";
import Card from "@/features/shared/Card";

interface TopologyGraphProps {
  telemetry: Telemetry;
}

/** Service dependency graph (blueprint §2, §4 demo script step 2): nodes = services, edges = deps,
 * color = anomaly. The failing service (named in telemetry.alerts[].target) lights up red. */
export default function TopologyGraph({ telemetry }: TopologyGraphProps) {
  const { nodes, edges, hasServices } = useMemo(() => {
    const services = (telemetry.topology?.services as string[] | undefined) ?? [];
    const edgesRaw = (telemetry.topology?.edges as [string, string][] | undefined) ?? [];
    const anomalous = new Set(
      (telemetry.alerts ?? []).map((a) => String((a as { target?: string }).target ?? "")).filter(Boolean),
    );
    const isAnomalousService = (service: string) => [...anomalous].some((t) => t.startsWith(service));

    const spacing = 190;
    const computedNodes: Node[] = services.map((service, i) => {
      const flagged = isAnomalousService(service);
      return {
        id: service,
        position: { x: i * spacing, y: (i % 2) * 90 },
        data: { label: service },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        style: {
          background: flagged ? "#2E1416" : "#171D26",
          color: flagged ? "#F87171" : "#E4E9EE",
          border: `1.5px solid ${flagged ? "#F87171" : "#232B36"}`,
          borderRadius: 6,
          fontSize: 11,
          fontFamily: '"JetBrains Mono", monospace',
          padding: "6px 10px",
          width: "auto",
        },
      };
    });

    const computedEdges: Edge[] = edgesRaw.map(([source, target], i) => ({
      id: `e-${i}`,
      source,
      target,
      animated: isAnomalousService(target) || isAnomalousService(source),
      style: { stroke: "#8A97A6" },
    }));

    return { nodes: computedNodes, edges: computedEdges, hasServices: services.length > 0 };
  }, [telemetry]);

  return (
    <Card title="Topology" padded={false}>
      <div style={{ height: 220 }}>
        {!hasServices ? (
          <div className="flex h-full items-center justify-center text-sm text-console-text-muted">
            No topology data.
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            fitView
            proOptions={{ hideAttribution: true }}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
          >
            <Background color="#232B36" gap={18} />
            <Controls showInteractive={false} />
          </ReactFlow>
        )}
      </div>
    </Card>
  );
}
