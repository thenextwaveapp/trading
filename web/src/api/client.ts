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

export async function fetchCandles(p: CandleParams): Promise<Candle[]> {
  const q = new URLSearchParams({ symbol: p.symbol, interval: p.interval });
  if (p.limit != null) q.set("limit", String(p.limit));
  if (p.start != null) q.set("start", String(p.start));
  if (p.end != null) q.set("end", String(p.end));
  const r = await fetch(`/candles?${q}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`/candles ${r.status}`);
  return r.json();
}
