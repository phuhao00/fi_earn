"use client";
import { useState, useEffect } from "react";
import { factorApi, type FactorResult } from "@/lib/api";
import { daysAgo, today } from "@/lib/utils";
import LineChart from "@/components/LineChart";
import BarChart from "@/components/BarChart";
import MetricCard from "@/components/MetricCard";

export default function FactorPage() {
  const [factors, setFactors] = useState<string[]>([]);
  const [symbol, setSymbol] = useState("000002");
  const [inputSymbol, setInputSymbol] = useState("000002");
  const [factor, setFactor] = useState("动量因子(20日)");
  const [holdPeriod, setHoldPeriod] = useState(5);
  const [nGroups, setNGroups] = useState(5);
  const [rollingWindow, setRollingWindow] = useState(20);
  const [periodDays, setPeriodDays] = useState(730);
  const [result, setResult] = useState<FactorResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    factorApi.list().then((res) => setFactors(res.factors));
  }, []);

  const handleCalculate = async () => {
    setLoading(true); setError(""); setResult(null);
    try {
      const res = await factorApi.calculate(
        symbol, factor, holdPeriod, nGroups, rollingWindow,
        daysAgo(periodDays), today()
      );
      setResult(res);
    } catch (e: any) {
      setError(e.message || "计算失败");
    } finally { setLoading(false); }
  };

  const rollingIcData = result?.rolling_ic.map((d) => ({ date: d.date, ic: d.ic })) ?? [];
  const groupData = result?.group_backtest.map((g) => ({ group: g.group, return_pct: g.return_pct })) ?? [];
  const factorTsData = result?.factor_series.map((d) => ({ date: d.date, value: d.value })) ?? [];
  const priceTsData = result?.price_series.map((d) => ({ date: d.date, value: d.value })) ?? [];

  const icMean = rollingIcData.length > 0
    ? rollingIcData.reduce((s, d) => s + d.ic, 0) / rollingIcData.length
    : null;

  return (
    <div className="flex h-full">
      {/* 左侧配置 */}
      <aside className="w-64 shrink-0 bg-[#1a1d24] border-r border-[#2d3140] p-5 overflow-auto space-y-5">
        <h2 className="text-sm font-semibold text-white">因子设置</h2>

        <div className="space-y-1">
          <label className="block text-xs text-slate-400">股票代码</label>
          <div className="flex gap-1">
            <input value={inputSymbol} onChange={(e) => setInputSymbol(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && setSymbol(inputSymbol)}
              className="flex-1 bg-[#0e1117] border border-[#2d3140] rounded-l-lg px-3 py-2 text-sm text-white focus:outline-none" />
            <button onClick={() => setSymbol(inputSymbol)} className="bg-blue-600 text-white text-xs px-2 rounded-r-lg">确定</button>
          </div>
        </div>

        <div className="space-y-2">
          <label className="block text-xs text-slate-400">时间范围</label>
          {[["近1年", 365], ["近2年", 730], ["近3年", 1095]].map(([l, d]) => (
            <button key={d} onClick={() => setPeriodDays(Number(d))}
              className={`w-full text-left px-3 py-1.5 text-xs rounded-lg border ${periodDays === d ? "bg-blue-600/20 border-blue-600 text-blue-400" : "border-[#2d3140] text-slate-400 hover:text-white"}`}>
              {l}
            </button>
          ))}
        </div>

        <div className="space-y-1">
          <label className="block text-xs text-slate-400">选择因子</label>
          <select value={factor} onChange={(e) => setFactor(e.target.value)}
            className="w-full bg-[#0e1117] border border-[#2d3140] rounded-lg px-3 py-2 text-sm text-white focus:outline-none">
            {factors.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </div>

        <div className="space-y-1">
          <label className="block text-xs text-slate-400">持有期（天）: {holdPeriod}</label>
          <input type="range" min={1} max={30} value={holdPeriod} onChange={(e) => setHoldPeriod(Number(e.target.value))}
            className="w-full accent-blue-500" />
        </div>

        <div className="space-y-1">
          <label className="block text-xs text-slate-400">分组数: {nGroups}</label>
          <input type="range" min={3} max={10} value={nGroups} onChange={(e) => setNGroups(Number(e.target.value))}
            className="w-full accent-blue-500" />
        </div>

        <div className="space-y-1">
          <label className="block text-xs text-slate-400">滚动IC窗口: {rollingWindow}</label>
          <input type="range" min={10} max={60} value={rollingWindow} onChange={(e) => setRollingWindow(Number(e.target.value))}
            className="w-full accent-blue-500" />
        </div>

        <button onClick={handleCalculate} disabled={loading}
          className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg py-2.5 text-sm font-medium transition-colors">
          {loading ? "计算中..." : "▶ 计算因子"}
        </button>
      </aside>

      {/* 右侧结果 */}
      <div className="flex-1 overflow-auto p-6 space-y-5">
        <h1 className="text-2xl font-bold text-white">因子研究</h1>
        <p className="text-sm text-slate-400">分析单因子的预测能力：IC 分析、分组收益、因子时序</p>

        {error && <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 text-red-400 text-sm">{error}</div>}

        {!result && !loading && !error && (
          <div className="bg-[#1a1d24] border border-[#2d3140] rounded-xl p-12 text-center text-slate-500">
            请在左侧配置参数，点击「计算因子」开始分析
          </div>
        )}

        {result && (
          <>
            {/* IC 指标卡 */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <MetricCard label="IC（Pearson）"
                value={result.ic != null ? result.ic.toFixed(4) : "N/A"}
                delta={result.ic != null && Math.abs(result.ic) > 0.05 ? "有效 (|IC|>0.05)" : "较弱"}
                deltaColor={result.ic != null && Math.abs(result.ic) > 0.05 ? "up" : "neutral"} />
              <MetricCard label="Rank IC（Spearman）"
                value={result.rank_ic != null ? result.rank_ic.toFixed(4) : "N/A"}
                delta={result.rank_ic != null && Math.abs(result.rank_ic) > 0.03 ? "有预测性" : "预测性弱"} />
              <MetricCard label="ICIR（信息比率）"
                value={result.icir.toFixed(4)}
                delta={Math.abs(result.icir) > 0.5 ? "稳定性好" : "稳定性一般"} />
              <MetricCard label="滚动IC均值"
                value={icMean != null ? icMean.toFixed(4) : "N/A"}
                deltaColor={icMean != null && icMean > 0 ? "up" : "down"} />
            </div>

            {/* 滚动IC + 分组回测 */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="bg-[#1a1d24] border border-[#2d3140] rounded-xl p-4">
                <div className="text-sm font-medium text-white mb-3">滚动 Rank IC（窗口={rollingWindow}天）</div>
                <BarChart data={rollingIcData} xKey="date" yKey="ic" height={260}
                  refLines={[{ value: 0, color: "#4a5568" }]} />
              </div>
              <div className="bg-[#1a1d24] border border-[#2d3140] rounded-xl p-4">
                <div className="text-sm font-medium text-white mb-3">
                  分组收益（{nGroups} 组，持有 {holdPeriod} 天）
                </div>
                <BarChart data={groupData} xKey="group" yKey="return_pct" height={260}
                  refLines={[{ value: 0, color: "#4a5568" }]} />
                <p className="text-xs text-slate-500 mt-2">Q1=因子最低组，Q{nGroups}=因子最高组，收益率(%)。多空差越大越有效。</p>
              </div>
            </div>

            {/* 因子时序 */}
            <div className="bg-[#1a1d24] border border-[#2d3140] rounded-xl p-4">
              <div className="text-sm font-medium text-white mb-3">价格走势</div>
              <LineChart data={priceTsData} series={[{ key: "value", label: "收盘价", color: "#3b82f6" }]} height={180} />
            </div>

            <div className="bg-[#1a1d24] border border-[#2d3140] rounded-xl p-4">
              <div className="text-sm font-medium text-white mb-3">因子值时序 — {factor}</div>
              <LineChart data={factorTsData} series={[{ key: "value", label: factor, color: "#f59e0b" }]} height={180}
                refLines={[{ value: 0, color: "#4a5568" }]} />
            </div>

            {/* 统计摘要 */}
            <div className="bg-[#1a1d24] border border-[#2d3140] rounded-xl p-4">
              <div className="text-sm font-medium text-white mb-3">因子统计摘要</div>
              <div className="grid grid-cols-3 lg:grid-cols-6 gap-3">
                {Object.entries(result.stats).map(([k, v]) => (
                  <MetricCard key={k} label={k} value={typeof v === "number" ? v.toFixed(4) : String(v)} />
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
