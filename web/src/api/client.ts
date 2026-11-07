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
  /** The instrument's market from the DB ("crypto" | "equity" | "fx_spot").
   *  Pass it when you have the row — it's the authoritative router. */
  market?: string;
}

const BINANCE_KLINES = "https://fapi.binance.com/fapi/v1/klines";

/** Does this instrument's data come from Binance (vs the server's Yahoo path)?
 *  The DB's market field is the answer when the caller has it; the USDT-suffix
 *  sniff is only a fallback for legacy crypto-only callers without the row. */
export const isBinance = (p: { symbol: string; market?: string }) =>
  p.market ? p.market === "crypto" : p.symbol.toUpperCase().endsWith("USDT");

export async function fetchCandles(p: CandleParams): Promise<Candle[]> {
  if (!isBinance(p)) {
    // Non-crypto (equities / FX) go through the server-side /candles endpoint,
    // which uses the engine's fetch_candles (Yahoo under the hood). Yahoo blocks
    // cross-origin, so the browser can't hit it directly — and the old /yf proxy
    // only existed in the Vite dev server, so prod charts were blank. /candles
    // works in dev and prod and already validates against the full tradeable set.
    const q = new URLSearchParams({ symbol: p.symbol, interval: p.interval });
    if (p.limit != null) q.set("limit", String(p.limit));
    if (p.start != null) q.set("start", String(p.start));
    if (p.end != null) q.set("end", String(p.end));
    const r = await fetch(`/candles?${q}`, { cache: "no-store" });
    if (!r.ok) return [];
    const rows: unknown[] = await r.json();
    return rows.map((x: any) => ({ t: Number(x.t), o: Number(x.o), h: Number(x.h), l: Number(x.l), c: Number(x.c) }));
  }
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

/** Deep history: Binance caps klines at ~1500 per request, so walk backward
 *  page by page (newest first) until maxCandles, the listing's start, or the
 *  request cap. Non-crypto symbols just pass the bigger limit to /candles —
 *  the server's Yahoo path returns what it has in one shot. */
export async function fetchCandlesDeep(p: {
  symbol: string;
  interval: string;
  maxCandles: number;
  market?: string;
}): Promise<Candle[]> {
  if (!isBinance(p)) {
    return fetchCandles({ symbol: p.symbol, interval: p.interval, limit: p.maxCandles, market: p.market });
  }
  const MAX_REQ = 8;
  const out: Candle[] = [];
  let end: number | undefined;
  for (let i = 0; i < MAX_REQ && out.length < p.maxCandles; i++) {
    const batch = await fetchCandles({ symbol: p.symbol, interval: p.interval, limit: 1500, end, market: p.market });
    if (!batch.length) break;
    out.unshift(...(end == null ? batch : batch.filter((c) => c.t < out[0].t)));
    if (batch.length < 1500) break; // reached the start of the listing
    end = out[0].t - 1;
  }
  return out.length > p.maxCandles ? out.slice(out.length - p.maxCandles) : out;
}
