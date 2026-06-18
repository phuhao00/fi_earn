"use client";
import { useState, useEffect, useCallback } from "react";
import { marketApi, type OHLCVRecord } from "@/lib/api";
import { daysAgo, today } from "@/lib/utils";
import CandlestickChart from "@/components/CandlestickChart";
import LineChart from "@/components/LineChart";
import BarChart from "@/components/BarChart";

type SubIndicator = "无" | "MACD" | "RSI" | "KDJ" | "成交量" | "OBV";

const PERIODS = [90, 180, 365, 730];
const PERIOD_LABELS = ["近3月", "近6月", "近1年", "近2年"];
const MA_OPTIONS = [5, 10, 20, 30, 60, 120];
const MA_COLORS: Record<number, string> = { 5: "#f59e0b", 10: "#3b82f6", 20: "#a855f7", 30: "#22c55e", 60: "#ef4444", 120: "#06b6d4" };

// ── 指标计算 ──────────────────────────────────────────────
function ema(vals: number[], n: number): number[] {
  const k = 2 / (n + 1);
  return vals.reduce((acc, v, i) => {
    if (i === 0) return [v];
    return [...acc, v * k + acc[i - 1] * (1 - k)];
  }, [] as number[]);
}

function calcMACD(close: number[], fast = 12, slow = 26, signal = 9) {
  const eFast = ema(close, fast);
  const eSlow = ema(close, slow);
  const dif = eFast.map((v, i) => v - eSlow[i]);
  const dea = ema(dif, signal);
  const hist = dif.map((v, i) => (v - dea[i]) * 2);
  return { dif, dea, hist };
}

function calcRSI(close: number[], n = 14): number[] {
  return close.map((_, i) => {
    if (i < n) return 50;
    const slice = close.slice(i - n, i);
    const gains = slice.map((v, j) => j > 0 && slice[j] > slice[j - 1] ? slice[j] - slice[j - 1] : 0);
    const losses = slice.map((v, j) => j > 0 && slice[j] < slice[j - 1] ? slice[j - 1] - slice[j] : 0);
    const ag = gains.reduce((s, v) => s + v, 0) / n;
    const al = losses.reduce((s, v) => s + v, 0) / n;
    return al === 0 ? 100 : 100 - 100 / (1 + ag / al);
  });
}

function calcKDJ(high: number[], low: number[], close: number[], n = 9) {
  const ks: number[] = [], ds: number[] = [], js: number[] = [];
  let k = 50, d = 50;
  for (let i = 0; i < close.length; i++) {
    const hl = high.slice(Math.max(0, i - n + 1), i + 1);
    const ll = low.slice(Math.max(0, i - n + 1), i + 1);
    const hh = Math.max(...hl), ll2 = Math.min(...ll);
    const rsv = hh === ll2 ? 50 : ((close[i] - ll2) / (hh - ll2)) * 100;
    k = (2 / 3) * k + (1 / 3) * rsv;
    d = (2 / 3) * d + (1 / 3) * k;
    ks.push(k); ds.push(d); js.push(3 * k - 2 * d);
  }
  return { k: ks, d: ds, j: js };
}

export default function TechnicalPage() {
  const [symbol, setSymbol] = useState("600519");
  const [inputSymbol, setInputSymbol] = useState("600519");
  const [periodIdx, setPeriodIdx] = useState(2);
  const [maPeriods, setMaPeriods] = useState<number[]>([5, 20, 60]);
  const [showBoll, setShowBoll] = useState(false);
  const [subIndicator, setSubIndicator] = useState<SubIndicator>("MACD");
  const [data, setData] = useState<OHLCVRecord[]>([]);
  const [loading, setLoading] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await marketApi.history(symbol, daysAgo(PERIODS[periodIdx]), today(), "qfq");
      setData(res.data);
    } catch {
      setData([]);
    } finally { setLoading(false); }
  }, [symbol, periodIdx]);

  useEffect(() => { loadData(); }, [loadData]);

  const close = data.map((d) => d.close);
  const maLines = maPeriods.map((p) => ({ period: p, color: MA_COLORS[p] }));

  // MACD 数据
  const macdData = close.length > 30
    ? calcMACD(close).hist.map((h, i) => ({ date: data[i].date.slice(0, 10), hist: +h.toFixed(4), dif: +calcMACD(close).dif[i].toFixed(4), dea: +calcMACD(close).dea[i].toFixed(4) }))
    : [];

  // RSI 数据
  const rsiData = close.length > 20
    ? calcRSI(close).map((v, i) => ({ date: data[i].date.slice(0, 10), rsi: +v.toFixed(2) }))
    : [];

  // KDJ
  const kdjRaw = close.length > 10
    ? calcKDJ(data.map((d) => d.high), data.map((d) => d.low), close)
    : null;
  const kdjData = kdjRaw
    ? close.map((_, i) => ({ date: data[i].date.slice(0, 10), K: +kdjRaw.k[i].toFixed(2), D: +kdjRaw.d[i].toFixed(2), J: +kdjRaw.j[i].toFixed(2) }))
    : [];

  // 成交量
  const volData = data.map((d) => ({ date: d.date.slice(0, 10), vol: d.volume ?? 0 }));

  // OBV
  const obvData = data.map((d, i) => {
    const prev = data[i - 1];
    const dir = i === 0 ? 0 : d.close > (prev?.close ?? 0) ? 1 : d.close < (prev?.close ?? 0) ? -1 : 0;
    return dir * (d.volume ?? 0);
  }).reduce((acc, v, i) => [...acc, { date: data[i].date.slice(0, 10), obv: (acc[i - 1]?.obv ?? 0) + v }], [] as { date: string; obv: number }[]);

  const lastMacd = macdData[macdData.length - 1];
  const lastRsi = rsiData[rsiData.length - 1];

  return (
    <div className="p-6 space-y-5">
      <h1 className="text-2xl font-bold text-white">技术分析</h1>

      {/* 控制栏 */}
      <div className="flex gap-3 flex-wrap items-center">
        <div className="flex gap-1">
          <input value={inputSymbol} onChange={(e) => setInputSymbol(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && setSymbol(inputSymbol)}
            placeholder="股票代码"
            className="bg-[#1a1d24] border border-[#2d3140] rounded-l-lg px-3 py-2 text-sm text-white w-36 focus:outline-none" />
          <button onClick={() => setSymbol(inputSymbol)}
            className="bg-blue-600 text-white text-sm px-3 py-2 rounded-r-lg hover:bg-blue-700">查询</button>
        </div>

        <div className="flex gap-1">
          {PERIOD_LABELS.map((l, i) => (
            <button key={i} onClick={() => setPeriodIdx(i)}
              className={`px-3 py-2 text-xs rounded-lg border ${periodIdx === i ? "bg-blue-600 border-blue-600 text-white" : "border-[#2d3140] text-slate-400 hover:text-white"}`}>
              {l}
            </button>
          ))}
        </div>

        <label className="flex items-center gap-2 text-sm text-slate-400 cursor-pointer">
          <input type="checkbox" checked={showBoll} onChange={(e) => setShowBoll(e.target.checked)} className="rounded" />
          BOLL
        </label>
      </div>

      {/* 均线选择 */}
      <div className="flex gap-2 items-center">
        <span className="text-xs text-slate-400">均线：</span>
        {MA_OPTIONS.map((p) => (
          <button key={p}
            onClick={() => setMaPeriods((prev) => prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p])}
            className="px-2.5 py-1 text-xs rounded border transition-colors"
            style={maPeriods.includes(p)
              ? { background: MA_COLORS[p] + "33", borderColor: MA_COLORS[p], color: MA_COLORS[p] }
              : { borderColor: "#2d3140", color: "#94a3b8" }}>
            MA{p}
          </button>
        ))}
      </div>

      {/* K 线图 */}
      <div className="bg-[#1a1d24] border border-[#2d3140] rounded-xl p-4">
        {loading ? (
          <div className="h-[420px] flex items-center justify-center text-slate-500">加载中...</div>
        ) : (
          <CandlestickChart data={data} maLines={maLines} height={420} />
        )}
      </div>

      {/* 副图指标选择 */}
      <div className="flex gap-2 items-center">
        <span className="text-xs text-slate-400">副图：</span>
        {(["无", "MACD", "RSI", "KDJ", "成交量", "OBV"] as SubIndicator[]).map((ind) => (
          <button key={ind} onClick={() => setSubIndicator(ind)}
            className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${subIndicator === ind ? "bg-blue-600 border-blue-600 text-white" : "border-[#2d3140] text-slate-400 hover:text-white"}`}>
            {ind}
          </button>
        ))}
      </div>

      {/* 副图 */}
      {subIndicator !== "无" && (
        <div className="bg-[#1a1d24] border border-[#2d3140] rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium text-white">{subIndicator}</span>
            {subIndicator === "MACD" && lastMacd && (
              <div className="flex gap-4 text-xs">
                <span className="text-yellow-400">DIF {lastMacd.dif}</span>
                <span className="text-blue-400">DEA {lastMacd.dea}</span>
                <span className={lastMacd.hist >= 0 ? "text-red-400" : "text-green-400"}>HIST {lastMacd.hist}</span>
              </div>
            )}
            {subIndicator === "RSI" && lastRsi && (
              <span className={`text-xs ${lastRsi.rsi > 70 ? "text-red-400" : lastRsi.rsi < 30 ? "text-green-400" : "text-slate-400"}`}>
                RSI {lastRsi.rsi} {lastRsi.rsi > 70 ? "（超买）" : lastRsi.rsi < 30 ? "（超卖）" : ""}
              </span>
            )}
          </div>

          {subIndicator === "MACD" && (
            <div>
              <BarChart data={macdData} xKey="date" yKey="hist" height={200}
                colorFn={(v) => v >= 0 ? "#ef535099" : "#26a69a99"} />
              <LineChart data={macdData} height={100}
                series={[{ key: "dif", label: "DIF", color: "#f59e0b" }, { key: "dea", label: "DEA", color: "#3b82f6" }]}
                refLines={[{ value: 0, color: "#4a5568" }]} />
            </div>
          )}

          {subIndicator === "RSI" && (
            <LineChart data={rsiData} series={[{ key: "rsi", label: "RSI(14)", color: "#a855f7" }]} height={220}
              refLines={[{ value: 70, color: "#ef4444" }, { value: 30, color: "#22c55e" }]} />
          )}

          {subIndicator === "KDJ" && (
            <LineChart data={kdjData} height={220}
              series={[{ key: "K", label: "K", color: "#f59e0b" }, { key: "D", label: "D", color: "#3b82f6" }, { key: "J", label: "J", color: "#ef4444" }]}
              refLines={[{ value: 80, color: "#ef4444" }, { value: 20, color: "#22c55e" }]} />
          )}

          {subIndicator === "成交量" && (
            <BarChart data={volData} xKey="date" yKey="vol" height={220} colorFn={() => "#3b82f666"} />
          )}

          {subIndicator === "OBV" && (
            <LineChart data={obvData} series={[{ key: "obv", label: "OBV", color: "#06b6d4" }]} height={220} />
          )}
        </div>
      )}
    </div>
  );
}
