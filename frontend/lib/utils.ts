import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function fmtPct(val: number, withSign = true): string {
  const sign = withSign && val > 0 ? "+" : "";
  return `${sign}${val.toFixed(2)}%`;
}

export function fmtNumber(val: number, decimals = 2): string {
  return val.toLocaleString("zh-CN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

export function fmtDate(dateStr: string): string {
  return dateStr.slice(0, 10);
}

/** 根据涨跌值返回颜色 class */
export function colorClass(val: number): string {
  if (val > 0) return "text-red-400";
  if (val < 0) return "text-green-400";
  return "text-gray-400";
}

/** 最近 N 天的日期字符串 */
export function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

export function today(): string {
  return new Date().toISOString().slice(0, 10);
}
