"use client";
import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  CrosshairMode,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type CandlestickData,
  type HistogramData,
  type Time,
} from "lightweight-charts";

interface OHLCVRecord {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

interface MALine {
  period: number;
  color: string;
}

interface Props {
  data: OHLCVRecord[];
  maLines?: MALine[];
  signals?: { date: string; price: number; signal: number }[];
  height?: number;
}

function calcMA(data: OHLCVRecord[], period: number) {
  return data
    .map((d, i) => {
      if (i < period - 1) return null;
      const slice = data.slice(i - period + 1, i + 1);
      const avg = slice.reduce((s, x) => s + x.close, 0) / period;
      return { time: d.date as Time, value: avg };
    })
    .filter(Boolean) as { time: Time; value: number }[];
}

export default function CandlestickChart({ data, maLines = [], signals = [], height = 480 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#0e1117" },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: { color: "#1e2433" },
        horzLines: { color: "#1e2433" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#2d3140" },
      timeScale: { borderColor: "#2d3140", timeVisible: true },
      width: containerRef.current.clientWidth,
      height,
    });
    chartRef.current = chart;

    // K 线（v5 API）
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#ef5350",
      downColor: "#26a69a",
      borderUpColor: "#ef5350",
      borderDownColor: "#26a69a",
      wickUpColor: "#ef5350",
      wickDownColor: "#26a69a",
    });
    candleSeries.setData(
      data.map((d) => ({
        time: d.date as Time,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
      }))
    );

    // 成交量
    if (data[0]?.volume !== undefined) {
      const volSeries = chart.addSeries(HistogramSeries, {
        color: "#3b82f6",
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
      });
      chart.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.8, bottom: 0 },
      });
      volSeries.setData(
        data.map((d) => ({
          time: d.date as Time,
          value: d.volume ?? 0,
          color: d.close >= d.open ? "#ef535066" : "#26a69a66",
        }))
      );
    }

    // 均线
    for (const { period, color } of maLines) {
      const maSeries = chart.addSeries(LineSeries, {
        color,
        lineWidth: 1,
        priceLineVisible: false,
      });
      maSeries.setData(calcMA(data, period));
    }

    // 信号覆盖线（买入=红色竖线，卖出=绿色竖线）
    // v5 移除了 setMarkers，通过叠加 LineSeries 近似标记
    if (signals.length > 0) {
      const buySeries = chart.addSeries(LineSeries, {
        color: "#ef535000", lineWidth: 1, priceLineVisible: false, crosshairMarkerVisible: false,
      });
      const buyPoints = signals
        .filter((s) => s.signal === 1)
        .map((s) => ({ time: s.date as Time, value: s.price }));
      if (buyPoints.length) buySeries.setData(buyPoints);

      const sellSeries = chart.addSeries(LineSeries, {
        color: "#26a69a00", lineWidth: 1, priceLineVisible: false, crosshairMarkerVisible: false,
      });
      const sellPoints = signals
        .filter((s) => s.signal === -1)
        .map((s) => ({ time: s.date as Time, value: s.price }));
      if (sellPoints.length) sellSeries.setData(sellPoints);
    }

    chart.timeScale().fitContent();

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [data, maLines, signals, height]);

  return <div ref={containerRef} className="w-full" style={{ height }} />;
}
