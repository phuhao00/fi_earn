"use client";
import { useState, useEffect, useCallback } from "react";
import { marketApi, type OHLCVRecord, type StockItem } from "@/lib/api";
import { daysAgo, today, colorClass, fmtPct } from "@/lib/utils";
import CandlestickChart from "@/components/CandlestickChart";
import MetricCard from "@/components/MetricCard";

const MA_COLORS: Record<number, string> = {
  5: "#f59e0b", 10: "#3b82f6", 20: "#a855f7", 30: "#22c55e", 60: "#ef4444",
};

const PERIODS = [
  { label: "近3月", days: 90 },
  { label: "近6月", days: 180 },
  { label: "近1年", days: 365 },
  { label: "近2年", days: 730 },
];

export default function MarketPage() {
  const [symbol, setSymbol] = useState("000002");
  const [inputVal, setInputVal] = useState("000002");
  const [searchResults, setSearchResults] = useState<StockItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [period, setPeriod] = useState(365);
  const [adjust, setAdjust] = useState("qfq");
  const [maPeriods, setMaPeriods] = useState<number[]>([5, 20, 60]);
  const [data, setData] = useState<OHLCVRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [quote, setQuote] = useState<Record<string, unknown>>({});

  const loadData = useCallback(async (sym: string) => {
    setLoading(true); setError("");
    try {
      const start = daysAgo(period);
      const end = today();
      const [histRes, quoteRes] = await Promise.allSettled([
        marketApi.history(sym, start, end, adjust),
        marketApi.quote(sym),
      ]);
      if (histRes.status === "fulfilled") setData(histRes.value.data);
      else setError(`行情加载失败: ${histRes.reason?.message}`);
      if (quoteRes.status === "fulfilled") setQuote(quoteRes.value.quote);
    } finally {
      setLoading(false);
    }
  }, [period, adjust]);

  useEffect(() => { loadData(symbol); }, [symbol, period, adjust, loadData]);

  const handleSearch = async (q: string) => {
    setInputVal(q);
    if (q.length < 1) { setSearchResults([]); return; }
    setSearching(true);
    try {
      const res = await marketApi.search(q);
      setSearchResults(res.results);
    } finally { setSearching(false); }
  };

  const handleSelect = (item: StockItem) => {
    setSymbol(item.code);
    setInputVal(`${item.code} ${item.name}`);
    setSearchResults([]);
  };

  const maLines = maPeriods.map((p) => ({ period: p, color: MA_COLORS[p] ?? "#888" }));

  const last = data.length > 0 ? data[data.length - 1] : null;
  const first = data.length > 0 ? data[0] : null;
  const periodChg = last && first ? (last.close / first.close - 1) * 100 : 0;

  return (
    <div className="p-6 space-y-5">
      <h1 className="text-2xl font-bold text-white">行情查询</h1>

      {/* 搜索栏 */}
      <div className="flex gap-3 flex-wrap items-start">
        <div className="relative">
          <input
            value={inputVal}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="股票代码或名称，如 000002"
            className="bg-[#1a1d24] border border-[#2d3140] rounded-lg px-4 py-2 text-sm text-white w-64 focus:outline-none focus:border-blue-500"
          />
          {searchResults.length > 0 && (
            <div className="absolute top-full mt-1 w-full bg-[#1a1d24] border border-[#2d3140] rounded-lg shadow-xl z-50 max-h-60 overflow-auto">
              {searchResults.map((s) => (
                <div key={s.code} className="px-3 py-2 text-sm cursor-pointer hover:bg-[#252a35] text-white flex justify-between"
                  onClick={() => handleSelect(s)}>
                  <span className="text-slate-400 font-mono">{s.code}</span>
                  <span>{s.name}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 时间周期 */}
        <div className="flex gap-2">
          {PERIODS.map((p) => (
            <button key={p.days} onClick={() => setPeriod(p.days)}
              className={`px-3 py-2 text-xs rounded-lg border transition-colors ${period === p.days ? "bg-blue-600 border-blue-600 text-white" : "border-[#2d3140] text-slate-400 hover:text-white"}`}>
              {p.label}
            </button>
          ))}
        </div>

        {/* 复权 */}
        <select value={adjust} onChange={(e) => setAdjust(e.target.value)}
          className="bg-[#1a1d24] border border-[#2d3140] rounded-lg px-3 py-2 text-sm text-white focus:outline-none">
          <option value="qfq">前复权</option>
          <option value="hfq">后复权</option>
          <option value="">不复权</option>
        </select>
      </div>

      {/* 均线选择 */}
      <div className="flex gap-2 items-center">
        <span className="text-xs text-slate-400">均线：</span>
        {[5, 10, 20, 30, 60].map((p) => (
          <button key={p}
            onClick={() => setMaPeriods((prev) => prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p])}
            className={`px-2.5 py-1 text-xs rounded border transition-colors`}
            style={maPeriods.includes(p) ? { backgroundColor: MA_COLORS[p] + "33", borderColor: MA_COLORS[p], color: MA_COLORS[p] } : { borderColor: "#2d3140", color: "#94a3b8" }}>
            MA{p}
          </button>
        ))}
      </div>

      {/* 行情指标卡 */}
      {last && (
        <div className="grid grid-cols-4 lg:grid-cols-6 gap-3">
          <MetricCard label="最新价" value={`¥${last.close.toFixed(2)}`}
            delta={quote?.["涨跌幅"] ? fmtPct(Number(quote["涨跌幅"])) : ""}
            deltaColor={Number(quote?.["涨跌幅"] ?? 0) > 0 ? "up" : "down"} />
          <MetricCard label="最高" value={`¥${last.high.toFixed(2)}`} />
          <MetricCard label="最低" value={`¥${last.low.toFixed(2)}`} />
          <MetricCard label="成交量" value={last.volume ? `${(last.volume / 1e4).toFixed(0)}万手` : "—"} />
          <MetricCard label="区间涨跌" value={fmtPct(periodChg)}
            deltaColor={periodChg > 0 ? "up" : "down"} />
          <MetricCard label="数据条数" value={String(data.length)} />
        </div>
      )}

      {/* K 线图 */}
      <div className="bg-[#1a1d24] border border-[#2d3140] rounded-xl p-4">
        {loading ? (
          <div className="h-[480px] flex items-center justify-center text-slate-500">加载中...</div>
        ) : error ? (
          <div className="h-[480px] flex items-center justify-center text-red-400">{error}</div>
        ) : data.length > 0 ? (
          <CandlestickChart data={data} maLines={maLines} height={480} />
        ) : (
          <div className="h-[480px] flex items-center justify-center text-slate-500">暂无数据</div>
        )}
      </div>

      {/* 数据表格 */}
      {data.length > 0 && (
        <div className="bg-[#1a1d24] border border-[#2d3140] rounded-xl overflow-hidden">
          <div className="px-4 py-3 text-sm font-medium text-white border-b border-[#2d3140]">最近 30 条数据</div>
          <div className="overflow-x-auto">
            <table>
              <thead><tr><th>日期</th><th className="text-right">开盘</th><th className="text-right">最高</th><th className="text-right">最低</th><th className="text-right">收盘</th><th className="text-right">涨跌幅</th><th className="text-right">成交量</th></tr></thead>
              <tbody>
                {data.slice(-30).reverse().map((r) => (
                  <tr key={r.date}>
                    <td className="font-mono text-slate-400">{String(r.date).slice(0, 10)}</td>
                    <td className="text-right font-mono">{r.open.toFixed(2)}</td>
                    <td className="text-right font-mono">{r.high.toFixed(2)}</td>
                    <td className="text-right font-mono">{r.low.toFixed(2)}</td>
                    <td className="text-right font-mono font-medium">{r.close.toFixed(2)}</td>
                    <td className={`text-right font-mono ${colorClass(r.pct_chg ?? 0)}`}>{r.pct_chg != null ? fmtPct(r.pct_chg) : "—"}</td>
                    <td className="text-right font-mono text-slate-400">{r.volume ? `${(r.volume / 1e4).toFixed(0)}万` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
