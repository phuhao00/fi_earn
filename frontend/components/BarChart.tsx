"use client";
import {
  BarChart as ReBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

interface DataPoint {
  [key: string]: string | number;
}

interface Props {
  data: DataPoint[];
  xKey: string;
  yKey: string;
  height?: number;
  colorFn?: (val: number) => string;
  label?: boolean;
  refLines?: { value: number; color?: string }[];
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-[#1a1d24] border border-[#2d3140] rounded-lg px-3 py-2 text-xs">
      <div className="text-slate-400 mb-1">{label}</div>
      <div style={{ color: payload[0].fill }} className="font-mono">
        {typeof payload[0].value === "number" ? payload[0].value.toFixed(4) : payload[0].value}
      </div>
    </div>
  );
};

export default function BarChart({ data, xKey, yKey, height = 260, colorFn, refLines = [] }: Props) {
  const defaultColor = (v: number) => (v >= 0 ? "#ef5350" : "#26a69a");
  const getColor = colorFn ?? defaultColor;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ReBarChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e2433" />
        <XAxis dataKey={xKey} tick={{ fill: "#94a3b8", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "#2d3140" }} />
        <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} tickLine={false} axisLine={false} />
        <Tooltip content={<CustomTooltip />} />
        {refLines.map((r, i) => (
          <ReferenceLine key={i} y={r.value} stroke={r.color || "#fff"} strokeDasharray="4 2" />
        ))}
        <Bar dataKey={yKey} radius={[3, 3, 0, 0]}>
          {data.map((d, i) => (
            <Cell key={i} fill={getColor(d[yKey] as number)} fillOpacity={0.8} />
          ))}
        </Bar>
      </ReBarChart>
    </ResponsiveContainer>
  );
}
