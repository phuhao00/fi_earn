"use client";
import { useEffect, useState, useCallback } from "react";
import { screenerApi, type ScreenerStock } from "@/lib/api";
import { colorClass, fmtPct } from "@/lib/utils";

// ─── 评分进度条 ────────────────────────────────────────────────────────────

function ScoreBar({ value, max = 100 }: { value: number; max?: number }) {
  const pct = Math.round((value / max) * 100);
  const color =
    pct >= 75 ? "bg-emerald-500" : pct >= 50 ? "bg-blue-500" : pct >= 30 ? "bg-amber-500" : "bg-slate-600";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-[#2d3140] rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-400 w-8 text-right">{value}</span>
    </div>
  );
}

// ─── 子维度标签 ─────────────────────────────────────────────────────────────

function DimTag({ label, value }: { label: string; value: number }) {
  const color =
    value >= 75 ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/30"
    : value >= 50 ? "text-blue-400 bg-blue-500/10 border-blue-500/30"
    : "text-slate-400 bg-slate-500/10 border-slate-500/30";
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs border ${color}`}>
      {label} <span className="font-mono font-medium">{value}</span>
    </span>
  );
}

// ─── 股票卡片 ───────────────────────────────────────────────────────────────

function StockCard({ stock }: { stock: ScreenerStock }) {
  const chgColor = stock.change_pct > 0 ? "text-red-400" : stock.change_pct < 0 ? "text-green-400" : "text-slate-400";
  const scoreColor =
    stock.total_score >= 75 ? "text-emerald-400"
    : stock.total_score >= 55 ? "text-blue-400"
    : "text-amber-400";

  return (
    <div className="bg-[#1a1d24] border border-[#2d3140] rounded-xl p-4 hover:border-blue-500/40 transition-colors">
      {/* 头部 */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-slate-500 bg-[#252a35] px-2 py-0.5 rounded">
            #{stock.rank}
          </span>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-semibold text-white text-sm">{stock.name}</span>
              <span className="text-xs text-slate-500 font-mono">{stock.code}</span>
            </div>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-sm font-mono text-white">{stock.price.toFixed(2)}</span>
              <span className={`text-xs font-mono ${chgColor}`}>
                {stock.change_pct > 0 ? "+" : ""}{fmtPct(stock.change_pct)}
              </span>
            </div>
          </div>
        </div>
        {/* 综合评分 */}
        <div className="text-right">
          <div className={`text-2xl font-bold ${scoreColor}`}>{stock.total_score}</div>
          <div className="text-xs text-slate-500">综合评分</div>
        </div>
      </div>

      {/* 综合评分条 */}
      <div className="mb-3">
        <ScoreBar value={stock.total_score} />
      </div>

      {/* 四维子分 */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        <DimTag label="趋势" value={stock.scores.trend} />
        <DimTag label="安全" value={stock.scores.safety} />
        <DimTag label="基本面" value={stock.scores.fundamental} />
        <DimTag label="热度" value={stock.scores.hotness} />
      </div>

      {/* 关键指标 */}
      <div className="grid grid-cols-4 gap-2 mb-3 text-center">
        <div>
          <div className="text-xs text-slate-500">PE</div>
          <div className="text-xs font-mono text-slate-300">{stock.metrics.pe}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500">PB</div>
          <div className="text-xs font-mono text-slate-300">{stock.metrics.pb}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500">RSI14</div>
          <div className={`text-xs font-mono ${stock.metrics.rsi14 > 70 ? "text-amber-400" : "text-slate-300"}`}>
            {stock.metrics.rsi14}
          </div>
        </div>
        <div>
          <div className="text-xs text-slate-500">60日涨</div>
          <div className={`text-xs font-mono ${colorClass(stock.metrics.gain_60d)}`}>
            {stock.metrics.gain_60d > 0 ? "+" : ""}{stock.metrics.gain_60d}%
          </div>
        </div>
      </div>

      {/* 均线多头 + 流通市值 */}
      <div className="flex items-center justify-between mb-3">
        <span className={`text-xs px-2 py-0.5 rounded border ${
          stock.metrics.ma_aligned
            ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/30"
            : "text-slate-500 bg-slate-500/10 border-slate-500/20"
        }`}>
          {stock.metrics.ma_aligned ? "均线多头排列" : "均线未排列"}
        </span>
        <span className="text-xs text-slate-500">
          流通市值 <span className="text-slate-400">{stock.metrics.float_cap_yi} 亿</span>
        </span>
      </div>

      {/* 理由 */}
      <p className="text-xs text-slate-400 bg-[#252a35] rounded-lg px-3 py-2 leading-relaxed">
        {stock.reason}
      </p>
    </div>
  );
}

// ─── 骨架屏 ─────────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="bg-[#1a1d24] border border-[#2d3140] rounded-xl p-4 animate-pulse">
      <div className="flex justify-between mb-3">
        <div className="space-y-2">
          <div className="h-4 w-32 bg-[#2d3140] rounded" />
          <div className="h-3 w-20 bg-[#2d3140] rounded" />
        </div>
        <div className="h-8 w-12 bg-[#2d3140] rounded" />
      </div>
      <div className="h-1.5 w-full bg-[#2d3140] rounded mb-3" />
      <div className="flex gap-1.5 mb-3">
        {[1, 2, 3, 4].map((i) => <div key={i} className="h-5 w-16 bg-[#2d3140] rounded" />)}
      </div>
      <div className="grid grid-cols-4 gap-2 mb-3">
        {[1, 2, 3, 4].map((i) => <div key={i} className="h-8 bg-[#2d3140] rounded" />)}
      </div>
      <div className="h-10 w-full bg-[#2d3140] rounded" />
    </div>
  );
}

// ─── 主页面 ─────────────────────────────────────────────────────────────────

export default function ScreenerPage() {
  const [result, setResult] = useState<{ updated_at: string; stocks: ScreenerStock[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (force = false) => {
    if (force) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const data = await screenerApi.top10(force);
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(false); }, [load]);

  const isLoading = loading;

  return (
    <div className="p-6 space-y-6">
      {/* 头部 */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">智能选股</h1>
          <p className="text-sm text-slate-400 mt-1">
            多因子模型 · 趋势 + 安全位 + 基本面 + 市场热度 · 自动排除垃圾股和高位股
          </p>
        </div>
        <button
          onClick={() => load(true)}
          disabled={refreshing || loading}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            refreshing || loading
              ? "bg-blue-600/30 text-blue-400/50 cursor-not-allowed"
              : "bg-blue-600 hover:bg-blue-700 text-white"
          }`}
        >
          {refreshing ? (
            <>
              <span className="inline-block w-3.5 h-3.5 border-2 border-blue-400/30 border-t-blue-400 rounded-full animate-spin" />
              筛选中...
            </>
          ) : "重新筛选"}
        </button>
      </div>

      {/* 更新时间 + 说明 */}
      {result && !isLoading && (
        <div className="flex items-center gap-4 text-xs text-slate-500">
          <span>上次更新：{result.updated_at.replace("T", " ")}</span>
          <span>共筛出 {result.stocks.length} 只股票</span>
          <span className="text-amber-500/70">· 重新筛选约需 15-30 秒（首次或缓存过期后）</span>
        </div>
      )}

      {/* 评分说明 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { label: "趋势分 30%", desc: "均线多头排列 + 近期涨幅适中" },
          { label: "安全位 25%", desc: "RSI 健康区间 + 非高位" },
          { label: "基本面 25%", desc: "PE/PB 估值合理 + 盈利" },
          { label: "热度分 20%", desc: "东财人气榜热点代理" },
        ].map((item) => (
          <div key={item.label} className="bg-[#1a1d24] border border-[#2d3140] rounded-lg px-3 py-2">
            <div className="text-xs font-medium text-blue-400">{item.label}</div>
            <div className="text-xs text-slate-500 mt-0.5">{item.desc}</div>
          </div>
        ))}
      </div>

      {/* 错误状态 */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400 text-sm">
          {error}
          <button onClick={() => load(false)} className="ml-3 underline hover:no-underline">重试</button>
        </div>
      )}

      {/* 股票卡片网格 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {isLoading
          ? Array.from({ length: 10 }).map((_, i) => <SkeletonCard key={i} />)
          : result?.stocks.map((stock) => <StockCard key={stock.code} stock={stock} />)
        }
      </div>

      {/* 免责声明 */}
      <p className="text-xs text-slate-600 pt-2">
        以上选股结果仅基于量化模型计算，不构成投资建议。股市有风险，投资需谨慎。过去表现不代表未来收益。
      </p>
    </div>
  );
}
