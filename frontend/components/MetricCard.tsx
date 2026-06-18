import { cn } from "@/lib/utils";

interface Props {
  label: string;
  value: string;
  delta?: string;
  deltaColor?: "up" | "down" | "neutral";
  className?: string;
}

export default function MetricCard({ label, value, delta, deltaColor, className }: Props) {
  const dc =
    deltaColor === "up" ? "text-red-400" :
    deltaColor === "down" ? "text-green-400" :
    "text-slate-400";

  return (
    <div className={cn("bg-[#1a1d24] border border-[#2d3140] rounded-xl p-4", className)}>
      <div className="text-xs text-slate-400 mb-1">{label}</div>
      <div className="text-xl font-semibold text-white">{value}</div>
      {delta && <div className={cn("text-xs mt-1", dc)}>{delta}</div>}
    </div>
  );
}
