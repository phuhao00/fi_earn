"use client";
import { useEffect, useState } from "react";
import { marketApi, type OHLCVRecord } from "@/lib/api";
import { colorClass, fmtPct, daysAgo, today } from "@/lib/utils";
import MetricCard from "@/components/MetricCard";
import LineChart from "@/components/LineChart";

const INDICES = [
  { label: "上证指数", code: "sh000001" },
  { label: "沪深300", code: "sh000300" },
  { label: "深证成指", code: "sz399001" },
  { label: "创业板指", code: "sz399006" },
  { label: "中证500", code: "sh000905" },
  { label: "科创50", code: "sh000688" },
];

interface IndexSnap { 代码?: string; 最新价?: number; 涨跌幅?: number; 名称?: string }
interface Mover { 代码: string; 名称: string; 最新价: number; 涨跌幅: number }

export default function HomePage() {
  const [snapshot, setSnapshot] = useState<IndexSnap[] | null>(null);
  const [movers, setMovers] = useState<{ gainers: Mover[]; losers: Mover[] } | null>(null);
  const [hs300, setHs300] = useState<OHLCVRecord[] | null>(null);
  const [cyb, setCyb] = useState<OHLCVRecord[] | null>(null);

  useEffect(() => {
    const start = daysAgo(365);
    const end = today();

    // 各模块独立加载，数据到了立刻渲染，不互相等待
    marketApi.indexSnapshot()
      .then((r) => setSnapshot((r.data ?? []) as IndexSnap[]))
      .catch(() => setSnapshot([]));

    marketApi.movers(10)
      .then((r) => setMovers(r as { gainers: Mover[]; losers: Mover[] }))
      .catch(() => setMovers({ gainers: [], losers: [] }));

    marketApi.indexHistory("sh000300", start, end)
      .then((r) => setHs300(r.data))
      .catch(() => setHs300([]));

    marketApi.indexHistory("sz399006", start, end)
      .then((r) => setCyb(r.data))
      .catch(() => setCyb([]));
  }, []);

  const hs300Chart = (hs300 ?? []).map((d) => ({ date: d.date.slice(0, 10), value: d.close }));
  const cybChart = (cyb ?? []).map((d) => ({ date: d.date.slice(0, 10), value: d.close }));

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">市场总览</h1>
        <p className="text-sm text-slate-400 mt-1">数据来源：AkShare（免费）· 每次访问自动刷新</p>
      </div>

      {/* 指数快照 */}
      <section>
        <h2 className="text-sm font-medium text-slate-400 uppercase tracking-wide mb-3">主要指数</h2>
        <div className="grid grid-cols-3 lg:grid-cols-6 gap-3">
          {INDICES.map((idx) => {
            const snap = (snapshot ?? []).find((s) => String(s.代码 ?? "").includes(idx.code.slice(-6)));
            const price = snap?.最新价 ?? 0;
            const chg = snap?.涨跌幅 ?? 0;
            return (
              <MetricCard
                key={idx.code}
                label={idx.label}
                value={snapshot === null ? "…" : price ? price.toLocaleString() : "—"}
                delta={chg ? fmtPct(Number(chg)) : ""}
                deltaColor={Number(chg) > 0 ? "up" : Number(chg) < 0 ? "down" : "neutral"}
              />
            );
          })}
        </div>
      </section>

      {/* 走势图 */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-[#1a1d24] border border-[#2d3140] rounded-xl p-4">
          <div className="text-sm font-medium text-white mb-3">沪深300 近一年走势</div>
          {hs300Chart.length > 0 ? (
            <LineChart data={hs300Chart} series={[{ key: "value", label: "沪深300", color: "#3b82f6" }]} height={220} />
          ) : (
            <div className="h-[220px] flex items-center justify-center text-slate-500 text-sm">
              {hs300 === null ? "加载中..." : "暂无数据"}
            </div>
          )}
        </div>
        <div className="bg-[#1a1d24] border border-[#2d3140] rounded-xl p-4">
          <div className="text-sm font-medium text-white mb-3">创业板指 近一年走势</div>
          {cybChart.length > 0 ? (
            <LineChart data={cybChart} series={[{ key: "value", label: "创业板指", color: "#f59e0b" }]} height={220} />
          ) : (
            <div className="h-[220px] flex items-center justify-center text-slate-500 text-sm">
              {cyb === null ? "加载中..." : "暂无数据"}
            </div>
          )}
        </div>
      </section>

      {/* 涨跌榜 */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-[#1a1d24] border border-[#2d3140] rounded-xl p-4">
          <div className="text-sm font-medium text-white mb-3">涨幅榜 TOP 10</div>
          <table>
            <thead><tr><th>代码</th><th>名称</th><th className="text-right">现价</th><th className="text-right">涨跌幅</th></tr></thead>
            <tbody>
              {movers === null || movers.gainers.length === 0 ? (
                <tr><td colSpan={4} className="text-center text-slate-500 py-8">{movers === null ? "加载中..." : "暂无数据（市场未开盘）"}</td></tr>
              ) : movers.gainers.map((m) => (
                <tr key={m.代码}>
                  <td className="text-slate-400 font-mono">{m.代码}</td>
                  <td>{m.名称}</td>
                  <td className="text-right font-mono">{Number(m.最新价).toFixed(2)}</td>
                  <td className={`text-right font-mono ${colorClass(Number(m.涨跌幅))}`}>{fmtPct(Number(m.涨跌幅))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="bg-[#1a1d24] border border-[#2d3140] rounded-xl p-4">
          <div className="text-sm font-medium text-white mb-3">跌幅榜 TOP 10</div>
          <table>
            <thead><tr><th>代码</th><th>名称</th><th className="text-right">现价</th><th className="text-right">涨跌幅</th></tr></thead>
            <tbody>
              {movers === null || movers.losers.length === 0 ? (
                <tr><td colSpan={4} className="text-center text-slate-500 py-8">{movers === null ? "加载中..." : "暂无数据（市场未开盘）"}</td></tr>
              ) : movers.losers.map((m) => (
                <tr key={m.代码}>
                  <td className="text-slate-400 font-mono">{m.代码}</td>
                  <td>{m.名称}</td>
                  <td className="text-right font-mono">{Number(m.最新价).toFixed(2)}</td>
                  <td className={`text-right font-mono ${colorClass(Number(m.涨跌幅))}`}>{fmtPct(Number(m.涨跌幅))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <p className="text-xs text-slate-600">数据仅供学习研究，不构成投资建议。市场有风险，投资需谨慎。</p>
    </div>
  );
}
