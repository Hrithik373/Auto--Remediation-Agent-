import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PreventionRow } from "@/mock/fixtures";
import Card from "@/features/shared/Card";

// Same validated 3-slot categorical set as ParetoChart (dataviz skill palette, dark steps,
// all-pairs-checked against this console's surface) -- fixed order, distinct dimension (which layer
// caught the action, not which baseline this is), reused for visual consistency across both figures.
const SEGMENT_COLOR = { caught_by_envelope: "#3987e5", caught_by_judge_only: "#d95926", missed: "#199e70" };
const SEGMENT_LABEL = { caught_by_envelope: "Caught by envelope", caught_by_judge_only: "Caught by judge only", missed: "Missed" };

interface PreventionPartitionProps {
  rows: PreventionRow[];
}

/** ★ The single most important figure in the project (blueprint §6.3): proves each verifier layer
 * earns its place. Envelope-only leaves a residue only the judge/learned layer catches. */
export default function PreventionPartition({ rows }: PreventionPartitionProps) {
  return (
    <Card title="Bad-action prevention, by layer">
      <div style={{ height: 240 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 8, right: 24, bottom: 8, left: 8 }} barCategoryGap="30%">
            <CartesianGrid stroke="#232B36" strokeDasharray="3 3" horizontal={false} />
            <XAxis
              type="number"
              domain={[0, 1]}
              tickFormatter={(v) => `${Math.round(v * 100)}%`}
              stroke="#8A97A6"
              fontSize={11}
            />
            <YAxis type="category" dataKey="baseline" stroke="#8A97A6" fontSize={11} width={110} />
            <Tooltip
              contentStyle={{ background: "#171D26", border: "1px solid #232B36", borderRadius: 6, fontSize: 12 }}
              formatter={(value: number, name) => [`${Math.round(value * 100)}%`, SEGMENT_LABEL[name as keyof typeof SEGMENT_LABEL] ?? name]}
            />
            <Legend
              formatter={(value) => SEGMENT_LABEL[value as keyof typeof SEGMENT_LABEL] ?? value}
              wrapperStyle={{ fontSize: 11, color: "#8A97A6" }}
            />
            <Bar dataKey="caught_by_envelope" stackId="a" fill={SEGMENT_COLOR.caught_by_envelope} stroke="#0B0F14" strokeWidth={2} />
            <Bar dataKey="caught_by_judge_only" stackId="a" fill={SEGMENT_COLOR.caught_by_judge_only} stroke="#0B0F14" strokeWidth={2} />
            <Bar dataKey="missed" stackId="a" fill={SEGMENT_COLOR.missed} stroke="#0B0F14" strokeWidth={2} radius={[0, 3, 3, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
