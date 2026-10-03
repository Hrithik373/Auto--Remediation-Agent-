import { CartesianGrid, Legend, Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ParetoPoint } from "@/mock/fixtures";
import { useUiStore } from "@/store/ui";
import Card from "@/features/shared/Card";

// Validated categorical series colors (dataviz skill references/palette.md, dark steps, slots 1-3:
// blue/orange/aqua) -- checked with scripts/validate_palette.js against this console's actual dark
// surface (#0B0F14) with --pairs all: lightness band, chroma floor, CVD separation, normal-vision
// floor, and contrast all PASS. Deliberately distinct from the decision/status hues in
// lib/decisionColors.ts so a chart series never impersonates allow/block/revise/escalate.
const SERIES_COLOR = ["#3987e5", "#d95926", "#199e70"];

function nearestPoint(points: ParetoPoint[], tau: number): ParetoPoint {
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
  const names = Object.entries(series);

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
            <Legend wrapperStyle={{ fontSize: 11, color: "#8A97A6" }} />
            {names.map(([name, points], i) => (
              <Line
                key={name}
                data={points}
                dataKey="bad_action_prevented"
                name={name}
                stroke={SERIES_COLOR[i % SERIES_COLOR.length]}
                strokeWidth={2}
                dot={{ r: 3 }}
                activeDot={{ r: 5 }}
                isAnimationActive={false}
              />
            ))}
            {names.map(([name, points], i) => {
              const p = nearestPoint(points, tau);
              return (
                <ReferenceDot
                  key={`marker-${name}`}
                  x={p.false_block}
                  y={p.bad_action_prevented}
                  r={7}
                  fill={SERIES_COLOR[i % SERIES_COLOR.length]}
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
