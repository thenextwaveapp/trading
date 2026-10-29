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
  if (!p.symbol.toUpperCase().endsWith("USDT")) {
    const ivMap: Record<string, [string, string]> = {
      "15m": ["15m", "60d"],
      "1h": ["1h", "730d"],
      "4h": ["1h", "730d"],
      "1d": ["1d", "5y"],
    };
    const [yfIv, yfRng] = ivMap[p.interval] ?? ["15m", "60d"];
    const r = await fetch(`/yf/v8/finance/chart/${encodeURIComponent(p.symbol)}?interval=${yfIv}&range=${yfRng}`, {
      cache: "no-store",
    });
    if (!r.ok) return [];
    const data = await r.json();
    const block = data?.chart?.result?.[0];
    if (!block) return [];
    const ts: number[] = block.timestamp ?? [];
    const q = block.indicators?.quote?.[0] ?? {};
    const out: Candle[] = [];
    for (let i = 0; i < ts.length; i++) {
      const o = q.open?.[i],
        h = q.high?.[i],
        l = q.low?.[i],
        c = q.close?.[i];
      if (o == null || h == null || l == null || c == null) continue;
      const t = ts[i] * 1000;
      if (p.start != null && t < p.start) continue;
      if (p.end != null && t > p.end) continue;
      out.push({ t, o: Number(o), h: Number(h), l: Number(l), c: Number(c) });
    }
    return p.limit != null && p.start == null ? out.slice(-p.limit) : out;
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
