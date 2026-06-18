"use client";
import {
  LineChart as ReLineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

interface DataPoint {
  date: string;
  [key: string]: number | string;
}

interface Series {
  key: string;
  label: string;
  color: string;
  dashed?: boolean;
}

interface Props {
  data: DataPoint[];
  series: Series[];
  height?: number;
  yLabel?: string;
  refLines?: { value: number; color?: string; label?: string }[];
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-[#1a1d24] border border-[#2d3140] rounded-lg px-3 py-2 text-xs">
      <div className="text-slate-400 mb-1">{label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} style={{ color: p.color }} className="flex justify-between gap-4">
          <span>{p.name}</span>
          <span className="font-mono">{typeof p.value === "number" ? p.value.toFixed(4) : p.value}</span>
        </div>
      ))}
    </div>
  );
};

export default function LineChart({ data, series, height = 300, yLabel, refLines = [] }: Props) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ReLineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e2433" />
        <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "#2d3140" }} interval="preserveStartEnd" />
        <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} tickLine={false} axisLine={false} label={yLabel ? { value: yLabel, angle: -90, fill: "#94a3b8", fontSize: 11 } : undefined} />
        <Tooltip content={<CustomTooltip />} />
        <Legend wrapperStyle={{ fontSize: 12, color: "#94a3b8" }} />
        {refLines.map((r, i) => (
          <ReferenceLine key={i} y={r.value} stroke={r.color || "#fff"} strokeDasharray="4 2" label={r.label} />
        ))}
        {series.map((s) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={s.color}
            dot={false}
            strokeWidth={1.8}
            strokeDasharray={s.dashed ? "5 3" : undefined}
          />
        ))}
      </ReLineChart>
    </ResponsiveContainer>
  );
}
