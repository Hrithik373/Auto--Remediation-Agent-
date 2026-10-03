import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PreventionRow } from "@/mock/fixtures";
import Card from "@/features/shared/Card";

// Validated with the dataviz skill's validate_palette.js on this card's surface (#11161D, dark mode),
// in THIS stack order (adjacency is what's checked): missed | envelope | secondary -- all checks PASS.
// "Missed" was green before, which read as "good"; it can't be red/amber/emerald/violet either, since
// those hues mean block/revise/allow/escalate (lib/decisionColors.ts). Magenta is the free hue, and it
// clears the gates only when NOT next to orange -- so "missed" sits first, against the baseline, which
// is also where the quantity that matters most is easiest to compare across bars.
const SEGMENT_COLOR = { missed: "#d55181", caught_by_envelope: "#3987e5", caught_by_secondary_only: "#d95926" };
// "Secondary" = whichever non-envelope layer was active (LLM judge and/or learned verifier): offline,
// it is the learned verifier, so this must not claim "judge".
const SEGMENT_LABEL = {
  caught_by_envelope: "Caught by envelope",
  caught_by_secondary_only: "Caught by judge/learned only",
  missed: "Missed (reached executor)",
};

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
            <YAxis type="category" dataKey="baseline" stroke="#8A97A6" fontSize={11} width={130} />
            <Tooltip
              contentStyle={{ background: "#171D26", border: "1px solid #232B36", borderRadius: 6, fontSize: 12 }}
              formatter={(value: number, name) => [`${Math.round(value * 100)}%`, SEGMENT_LABEL[name as keyof typeof SEGMENT_LABEL] ?? name]}
            />
            <Legend
              formatter={(value) => SEGMENT_LABEL[value as keyof typeof SEGMENT_LABEL] ?? value}
              wrapperStyle={{ fontSize: 11, color: "#8A97A6" }}
            />
            <Bar dataKey="missed" stackId="a" fill={SEGMENT_COLOR.missed} stroke="#0B0F14" strokeWidth={2} isAnimationActive={false} />
            <Bar dataKey="caught_by_envelope" stackId="a" fill={SEGMENT_COLOR.caught_by_envelope} stroke="#0B0F14" strokeWidth={2} isAnimationActive={false} />
            <Bar dataKey="caught_by_secondary_only" stackId="a" fill={SEGMENT_COLOR.caught_by_secondary_only} stroke="#0B0F14" strokeWidth={2} radius={[0, 3, 3, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
