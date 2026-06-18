/**
 * API 客户端 - 封装所有后端请求
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `请求失败: ${res.status}`);
  }
  return res.json();
}

// ─── 市场数据 ─────────────────────────────────────────────
export interface OHLCVRecord {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  pct_chg?: number;
  amount?: number;
}

export interface StockItem {
  code: string;
  name: string;
}

export interface MoverItem {
  代码: string;
  名称: string;
  最新价: number;
  涨跌幅: number;
  成交量: number;
}

export const marketApi = {
  history: (symbol: string, startDate?: string, endDate?: string, adjust = "qfq") =>
    request<{ symbol: string; data: OHLCVRecord[] }>(
      `/api/market/history?symbol=${symbol}&adjust=${adjust}` +
        (startDate ? `&start_date=${startDate}` : "") +
        (endDate ? `&end_date=${endDate}` : "")
    ),

  quote: (symbol: string) =>
    request<{ symbol: string; quote: Record<string, unknown> }>(
      `/api/market/quote?symbol=${symbol}`
    ),

  stocks: () => request<{ data: StockItem[] }>("/api/market/stocks"),

  search: (q: string) =>
    request<{ results: StockItem[] }>(`/api/market/search?q=${encodeURIComponent(q)}`),

  indexHistory: (code = "sh000300", startDate?: string, endDate?: string) =>
    request<{ code: string; data: OHLCVRecord[] }>(
      `/api/market/index/history?code=${code}` +
        (startDate ? `&start_date=${startDate}` : "") +
        (endDate ? `&end_date=${endDate}` : "")
    ),

  indexSnapshot: () =>
    request<{ data: Record<string, unknown>[] }>("/api/market/index/snapshot"),

  movers: (topN = 10) =>
    request<{ gainers: MoverItem[]; losers: MoverItem[] }>(
      `/api/market/movers?top_n=${topN}`
    ),
};

// ─── 策略回测 ─────────────────────────────────────────────
export interface StrategyParam {
  name: string;
  label: string;
  default: number | string;
  type: "int" | "float" | "select";
  min?: number;
  max?: number;
  step?: number;
  options?: string[];
  description?: string;
}

export interface Strategy {
  name: string;
  description: string;
  params: StrategyParam[];
}

export interface BacktestRequest {
  symbol: string;
  strategy_name: string;
  params: Record<string, number | string>;
  start_date?: string;
  end_date?: string;
  initial_capital: number;
  commission_rate: number;
  with_benchmark: boolean;
}

export interface BacktestResult {
  metrics: Record<string, string>;
  equity_curve: { date: string; equity: number }[];
  benchmark_curve: { date: string; value: number }[] | null;
  signals: { date: string; price: number; signal: number }[];
  trades: {
    entry_date: string;
    exit_date: string;
    entry_price: number;
    exit_price: number;
    shares: number;
    profit_pct: number;
    profit_amount: number;
  }[];
}

export const backtestApi = {
  strategies: () => request<{ strategies: Strategy[] }>("/api/backtest/strategies"),

  run: (body: BacktestRequest) =>
    request<BacktestResult>("/api/backtest/run", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

// ─── 因子研究 ─────────────────────────────────────────────
export interface FactorResult {
  ic: number | null;
  rank_ic: number | null;
  icir: number;
  rolling_ic: { date: string; ic: number }[];
  group_backtest: { group: string; return_pct: number }[];
  factor_series: { date: string; value: number }[];
  price_series: { date: string; value: number }[];
  stats: Record<string, number>;
}

export const factorApi = {
  list: () => request<{ factors: string[] }>("/api/factor/factors"),

  calculate: (
    symbol: string,
    factor: string,
    holdPeriod = 5,
    nGroups = 5,
    rollingWindow = 20,
    startDate?: string,
    endDate?: string
  ) =>
    request<FactorResult>(
      `/api/factor/calculate?symbol=${symbol}&factor=${encodeURIComponent(factor)}&hold_period=${holdPeriod}&n_groups=${nGroups}&rolling_window=${rollingWindow}` +
        (startDate ? `&start_date=${startDate}` : "") +
        (endDate ? `&end_date=${endDate}` : "")
    ),
};

// ─── 智能选股 ─────────────────────────────────────────────
export interface StockScores {
  trend: number;
  safety: number;
  fundamental: number;
  hotness: number;
}

export interface StockMetrics {
  pe: number;
  pb: number;
  float_cap_yi: number;
  rsi14: number;
  ma_aligned: boolean;
  gain_60d: number;
  amount_yi: number;
}

export interface ScreenerStock {
  rank: number;
  code: string;
  name: string;
  price: number;
  change_pct: number;
  total_score: number;
  scores: StockScores;
  metrics: StockMetrics;
  reason: string;
}

export interface ScreenerResult {
  updated_at: string;
  total: number;
  stocks: ScreenerStock[];
}

export const screenerApi = {
  top10: (force = false) =>
    request<ScreenerResult>(`/api/screener/top10${force ? "?force=true" : ""}`),
};
