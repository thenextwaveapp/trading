import type { Candle, Payload } from "./types";

export async function fetchPayload(signal?: AbortSignal): Promise<Payload> {
  const r = await fetch("/api", { cache: "no-store", signal });
  if (!r.ok) throw new Error(`/api ${r.status}`);
  return r.json();
}

export interface CandleParams {
  symbol: string;
  interval: string;
  limit?: number;
  start?: number;
  end?: number;
}

const BINANCE_KLINES = "https://fapi.binance.com/fapi/v1/klines";

export async function fetchCandles(p: CandleParams): Promise<Candle[]> {
  const q = new URLSearchParams({ symbol: p.symbol, interval: p.interval });
  if (p.limit != null) q.set("limit", String(p.limit));
  if (p.start != null) q.set("startTime", String(p.start));
  if (p.end != null) q.set("endTime", String(p.end));
  const r = await fetch(`${BINANCE_KLINES}?${q}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`klines ${r.status}`);
  const rows: unknown[] = await r.json();
  return rows.map((x: any) => ({
    t: Number(x[0]),
    o: Number(x[1]),
    h: Number(x[2]),
    l: Number(x[3]),
    c: Number(x[4]),
  }));
}
