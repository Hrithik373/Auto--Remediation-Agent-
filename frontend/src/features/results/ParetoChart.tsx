import { CartesianGrid, Legend, Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ParetoPoint } from "@/mock/fixtures";
import { useUiStore } from "@/store/ui";
import Card from "@/features/shared/Card";

// Validated categorical series colors (dataviz skill references/palette.md, dark steps, slots 1-3:
// blue/orange/aqua) -- checked with scripts/validate_palette.js against this console's actual dark
// surface (#0B0F14) with --pairs all: lightness band, chroma floor, CVD separation, normal-vision
// floor, and contrast all PASS. Deliberately distinct from the decision/status hues in
// lib/decisionColors.ts so a chart series never impersonates allow/block/revise/escalate.
// Keyed by ENTITY (verifier variant), never by series index: a filter or a missing variant must not
// repaint the survivors (dataviz rule "color follows the entity, never its rank").
const SERIES_COLOR: Record<string, string> = { envelope: "#3987e5", learned: "#d95926", llm_judge: "#199e70" };
const SERIES_NAME: Record<string, string> = {
  envelope: "Envelope only",
  learned: "Envelope + learned",
  llm_judge: "Envelope + LLM judge",
};
const FALLBACK_COLOR = "#8A97A6";

type PlottedPoint = ParetoPoint & { false_block: number; bad_action_prevented: number };

function plotted(points: ParetoPoint[]): PlottedPoint[] {
  return points.filter((p): p is PlottedPoint => p.false_block != null && p.bad_action_prevented != null);
}

function nearestPoint(points: PlottedPoint[], tau: number): PlottedPoint | undefined {
  if (points.length === 0) return undefined;
  return points.reduce((best, p) => (Math.abs(p.tau - tau) < Math.abs(best.tau - tau) ? p : best));
}

interface ParetoChartProps {
  series: Record<string, ParetoPoint[]>;
}

/** ★ The results thesis, part 1 (blueprint §6.3): bad-action-prevented vs. false-block across τ, one
 * series per verifier variant. The τ slider is the "trade-off knob" viva moment -- it's the same
 * Zustand `tau` RunControls drives, so dragging it here or there stays in sync everywhere. */
export default function ParetoChart({ series }: ParetoChartProps) {
  const { tau, setTau } = useUiStore();
  const names = Object.entries(series).map(([variant, points]) => [variant, plotted(points)] as const);

  return (
    <Card title="Risk–autonomy Pareto">
      <div className="mb-3 flex items-center gap-3">
        <label className="text-2xs uppercase tracking-wider text-console-text-muted">τ marker</label>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={tau}
          onChange={(e) => setTau(Number(e.target.value))}
          className="w-40 accent-accent"
        />
        <span className="font-mono text-xs text-console-text">{tau.toFixed(2)}</span>
      </div>

      <div style={{ height: 280 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid stroke="#232B36" strokeDasharray="3 3" />
            <XAxis
              type="number"
              dataKey="false_block"
              domain={[0, "dataMax"]}
              tickFormatter={(v) => `${Math.round(v * 100)}%`}
              stroke="#8A97A6"
              fontSize={11}
              label={{ value: "false-block rate", position: "insideBottom", offset: -4, fill: "#8A97A6", fontSize: 11 }}
            />
            <YAxis
              type="number"
              dataKey="bad_action_prevented"
              domain={[0, 1]}
              tickFormatter={(v) => `${Math.round(v * 100)}%`}
              stroke="#8A97A6"
              fontSize={11}
              label={{ value: "bad-action-prevented", angle: -90, position: "insideLeft", fill: "#8A97A6", fontSize: 11 }}
            />
            <Tooltip
              contentStyle={{ background: "#171D26", border: "1px solid #232B36", borderRadius: 6, fontSize: 12 }}
              formatter={(value: number, name) => [`${Math.round(value * 100)}%`, name]}
              labelFormatter={() => ""}
            />
            <Legend verticalAlign="top" height={28} wrapperStyle={{ fontSize: 11, color: "#8A97A6" }} />
            {names.map(([variant, points]) => (
              <Line
                key={variant}
                data={points}
                dataKey="bad_action_prevented"
                name={SERIES_NAME[variant] ?? variant}
                stroke={SERIES_COLOR[variant] ?? FALLBACK_COLOR}
                strokeWidth={2}
                dot={{ r: 3 }}
                activeDot={{ r: 5 }}
                isAnimationActive={false}
              />
            ))}
            {names.map(([variant, points]) => {
              const p = nearestPoint(points, tau);
              if (!p) return null;
              return (
                <ReferenceDot
                  key={`marker-${variant}`}
                  x={p.false_block}
                  y={p.bad_action_prevented}
                  r={7}
                  fill={SERIES_COLOR[variant] ?? FALLBACK_COLOR}
                  stroke="#0B0F14"
                  strokeWidth={2}
                  isFront
                />
              );
            })}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
