import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatAxis, formatCell } from "../lib/format";

// No entry animation: a half-drawn bar would show the wrong value (and respects reduced motion).
const ACCENT = "#34d399";
const GRID = "rgba(148, 168, 156, 0.12)";
const TICK = { fill: "#8a9b90", fontSize: 11 };

interface Props {
  type: "bar" | "line";
  data: { x: string; y: number | null }[];
  yLabel: string;
}

export default function ChartView({ type, data, yLabel }: Props) {
  const many = data.length > 8;
  const tooltip = (
    <Tooltip
      cursor={{ fill: "rgba(52, 211, 153, 0.06)" }}
      contentStyle={{
        background: "#0b0f0d",
        border: "1px solid rgba(148,168,156,.2)",
        borderRadius: 10,
      }}
      labelStyle={{ color: "#e8f0eb" }}
      formatter={(v) => [formatCell(v as number, yLabel), yLabel]}
    />
  );
  const xAxis = (
    <XAxis
      dataKey="x"
      tick={TICK}
      tickLine={false}
      axisLine={{ stroke: GRID }}
      interval={many ? "preserveStartEnd" : 0}
      angle={many && type === "bar" ? -35 : 0}
      textAnchor={many && type === "bar" ? "end" : "middle"}
      height={many && type === "bar" ? 70 : 30}
    />
  );
  const yAxis = (
    <YAxis tick={TICK} tickLine={false} axisLine={false} tickFormatter={formatAxis} width={56} />
  );
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        {type === "bar" ? (
          <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            {xAxis}
            {yAxis}
            {tooltip}
            <Bar
              dataKey="y"
              fill={ACCENT}
              radius={[4, 4, 0, 0]}
              maxBarSize={48}
              isAnimationActive={false}
            />
          </BarChart>
        ) : (
          <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            {xAxis}
            {yAxis}
            {tooltip}
            <Line
              dataKey="y"
              stroke={ACCENT}
              strokeWidth={2}
              dot={{ r: 3, fill: ACCENT }}
              isAnimationActive={false}
            />
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
