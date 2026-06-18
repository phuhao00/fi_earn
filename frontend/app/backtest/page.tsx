"use client";
import { useState, useEffect } from "react";
import { backtestApi, type Strategy, type BacktestResult } from "@/lib/api";
import { daysAgo, today } from "@/lib/utils";
import LineChart from "@/components/LineChart";
import MetricCard from "@/components/MetricCard";
import BarChart from "@/components/BarChart";

export default function BacktestPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selected, setSelected] = useState<Strategy | null>(null);
  const [params, setParams] = useState<Record<string, number | string>>({});
  const [symbol, setSymbol] = useState("000300");
  const [periodDays, setPeriodDays] = useState(730);
  const [capital, setCapital] = useState(100000);
  const [commission, setCommission] = useState(0.0003);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    backtestApi.strategies().then((res) => {
      setStrategies(res.strategies);
      if (res.strategies.length > 0) {
        const first = res.strategies[0];
        setSelected(first);
        const defaults: Record<string, number | string> = {};
        first.params.forEach((p) => { defaults[p.name] = p.default; });
        setParams(defaults);
      }
    });
  }, []);

  const handleStrategyChange = (name: string) => {
    const s = strategies.find((s) => s.name === name);
    if (!s) return;
    setSelected(s);
    const defaults: Record<string, number | string> = {};
    s.params.forEach((p) => { defaults[p.name] = p.default; });
    setParams(defaults);
    setResult(null);
  };

  const handleRun = async () => {
    if (!selected) return;
    setLoading(true); setError(""); setResult(null);
    try {
      const res = await backtestApi.run({
        symbol,
        strategy_name: selected.name,
        params,
        start_date: daysAgo(periodDays),
        end_date: today(),
        initial_capital: capital,
        commission_rate: commission,
        with_benchmark: true,
      });
      setResult(res);
    } catch (e: any) {
      setError(e.message || "回测失败");
    } finally { setLoading(false); }
  };

  // 净值曲线数据合并
  const equityData = result?.equity_curve.map((d) => {
    const bench = result.benchmark_curve?.find((b) => b.date === d.date);
    return { date: d.date, 策略净值: d.equity, ...(bench ? { 沪深300: bench.value } : {}) };
  }) ?? [];

  // 回撤数据
  const drawdownData = result?.equity_curve.reduce((acc, d) => {
    const peak = acc.length === 0 ? d.equity : Math.max(acc[acc.length - 1].peak, d.equity);
    const dd = ((d.equity - peak) / peak) * 100;
    return [...acc, { date: d.date, peak, 回撤: +dd.toFixed(4) }];
  }, [] as { date: string; peak: number; 回撤: number }[]) ?? [];

  return (
    <div className="flex h-full">
      {/* 左侧配置面板 */}
      <aside className="w-64 shrink-0 bg-[#1a1d24] border-r border-[#2d3140] p-5 overflow-auto space-y-5">
        <h2 className="text-sm font-semibold text-white">回测配置</h2>

        <div className="space-y-3">
          <label className="block text-xs text-slate-400">股票/指数代码</label>
          <input value={symbol} onChange={(e) => setSymbol(e.target.value)}
            className="w-full bg-[#0e1117] border border-[#2d3140] rounded-lg px-3 py-2 text-sm text-white focus:outline-none" />
        </div>

        <div className="space-y-2">
          <label className="block text-xs text-slate-400">时间范围</label>
          {[["近1年", 365], ["近2年", 730], ["近3年", 1095], ["近5年", 1825]].map(([l, d]) => (
            <button key={d} onClick={() => setPeriodDays(Number(d))}
              className={`w-full text-left px-3 py-1.5 text-xs rounded-lg border transition-colors ${periodDays === d ? "bg-blue-600/20 border-blue-600 text-blue-400" : "border-[#2d3140] text-slate-400 hover:text-white"}`}>
              {l}
            </button>
          ))}
        </div>

        <div className="space-y-1">
          <label className="block text-xs text-slate-400">初始资金（元）</label>
          <input type="number" value={capital} onChange={(e) => setCapital(Number(e.target.value))}
            className="w-full bg-[#0e1117] border border-[#2d3140] rounded-lg px-3 py-2 text-sm text-white focus:outline-none" />
        </div>

        <div className="space-y-1">
          <label className="block text-xs text-slate-400">手续费率</label>
          <input type="number" value={commission} step={0.0001} onChange={(e) => setCommission(Number(e.target.value))}
            className="w-full bg-[#0e1117] border border-[#2d3140] rounded-lg px-3 py-2 text-sm text-white focus:outline-none" />
        </div>

        <div className="space-y-1">
          <label className="block text-xs text-slate-400">策略</label>
          <select value={selected?.name ?? ""} onChange={(e) => handleStrategyChange(e.target.value)}
            className="w-full bg-[#0e1117] border border-[#2d3140] rounded-lg px-3 py-2 text-sm text-white focus:outline-none">
            {strategies.map((s) => <option key={s.name} value={s.name}>{s.name}</option>)}
          </select>
          {selected && <p className="text-xs text-slate-500 mt-1">{selected.description}</p>}
        </div>

        {/* 策略参数 */}
        {selected?.params.map((p) => (
          <div key={p.name} className="space-y-1">
            <label className="block text-xs text-slate-400">{p.label}</label>
            {p.type === "select" ? (
              <select value={String(params[p.name] ?? p.default)}
                onChange={(e) => setParams({ ...params, [p.name]: e.target.value })}
                className="w-full bg-[#0e1117] border border-[#2d3140] rounded-lg px-3 py-2 text-sm text-white focus:outline-none">
                {p.options?.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            ) : (
              <input type="number" value={Number(params[p.name] ?? p.default)}
                min={p.min ?? undefined} max={p.max ?? undefined} step={p.step ?? 1}
                onChange={(e) => setParams({ ...params, [p.name]: Number(e.target.value) })}
                className="w-full bg-[#0e1117] border border-[#2d3140] rounded-lg px-3 py-2 text-sm text-white focus:outline-none" />
            )}
          </div>
        ))}

        <button onClick={handleRun} disabled={loading}
          className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg py-2.5 text-sm font-medium transition-colors">
          {loading ? "计算中..." : "▶ 运行回测"}
        </button>
      </aside>

      {/* 右侧结果区域 */}
      <div className="flex-1 overflow-auto p-6 space-y-5">
        <h1 className="text-2xl font-bold text-white">策略回测</h1>

        {error && <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 text-red-400 text-sm">{error}</div>}

        {!result && !loading && !error && (
          <div className="bg-[#1a1d24] border border-[#2d3140] rounded-xl p-12 text-center text-slate-500">
            请在左侧配置参数，点击「运行回测」开始
          </div>
        )}

        {result && (
          <>
            {/* 绩效指标 */}
            <div className="grid grid-cols-4 lg:grid-cols-7 gap-3">
              {Object.entries(result.metrics).map(([k, v]) => (
                <MetricCard key={k} label={k} value={v}
                  deltaColor={k.includes("收益") ? (v.startsWith("-") ? "down" : "up") : undefined} />
              ))}
            </div>

            {/* 净值曲线 */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2 bg-[#1a1d24] border border-[#2d3140] rounded-xl p-4">
                <div className="text-sm font-medium text-white mb-3">策略净值曲线</div>
                <LineChart data={equityData} height={300}
                  series={[
                    { key: "策略净值", label: "策略净值", color: "#3b82f6" },
                    ...(result.benchmark_curve ? [{ key: "沪深300", label: "沪深300", color: "#94a3b8", dashed: true }] : []),
                  ]}
                  refLines={[{ value: 1, color: "#4a5568" }]} />
              </div>
              <div className="bg-[#1a1d24] border border-[#2d3140] rounded-xl p-4">
                <div className="text-sm font-medium text-white mb-3">回撤曲线</div>
                <LineChart data={drawdownData} series={[{ key: "回撤", label: "回撤 (%)", color: "#26a69a" }]} height={300}
                  refLines={[{ value: 0, color: "#4a5568" }]} />
              </div>
            </div>

            {/* 交易明细 */}
            {result.trades.length > 0 && (
              <>
                {/* 收益分布 */}
                <div className="bg-[#1a1d24] border border-[#2d3140] rounded-xl p-4">
                  <div className="text-sm font-medium text-white mb-3">单笔收益率分布</div>
                  <BarChart
                    data={result.trades.map((t, i) => ({ id: `#${i + 1}`, profit: t.profit_pct }))}
                    xKey="id" yKey="profit" height={200} />
                </div>

                <div className="bg-[#1a1d24] border border-[#2d3140] rounded-xl overflow-hidden">
                  <div className="px-4 py-3 text-sm font-medium text-white border-b border-[#2d3140]">交易记录（共 {result.trades.length} 笔）</div>
                  <div className="overflow-x-auto">
                    <table>
                      <thead>
                        <tr>
                          <th>买入日期</th><th>卖出日期</th>
                          <th className="text-right">买入价</th><th className="text-right">卖出价</th>
                          <th className="text-right">股数</th><th className="text-right">收益率</th>
                          <th className="text-right">盈亏金额</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.trades.map((t, i) => (
                          <tr key={i}>
                            <td className="font-mono text-slate-400">{t.entry_date}</td>
                            <td className="font-mono text-slate-400">{t.exit_date}</td>
                            <td className="text-right font-mono">{t.entry_price.toFixed(2)}</td>
                            <td className="text-right font-mono">{t.exit_price.toFixed(2)}</td>
                            <td className="text-right font-mono">{t.shares}</td>
                            <td className={`text-right font-mono ${t.profit_pct >= 0 ? "text-red-400" : "text-green-400"}`}>
                              {t.profit_pct >= 0 ? "+" : ""}{t.profit_pct.toFixed(2)}%
                            </td>
                            <td className={`text-right font-mono ${t.profit_amount >= 0 ? "text-red-400" : "text-green-400"}`}>
                              ¥{t.profit_amount >= 0 ? "+" : ""}{t.profit_amount.toFixed(0)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
