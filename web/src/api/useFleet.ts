import { useEffect, useRef, useState } from "react";
import { supabase } from "../db/supabase";
import type { Payload, Position, Trade, Variant } from "./types";
import type { DbBot, DbBotMark } from "../db/types";

export interface FleetState {
  data: Payload | null;
  error: string | null;
  loading: boolean;
}

const START = 10000;

function buildPayload(
  bots: DbBot[],
  marks: DbBotMark[],
  trades: any[],
  symbols: Record<string, string>,
  prices: Record<string, number>,
): Payload {
  const latestMark = new Map<string, DbBotMark>();
  const marksByBot = new Map<string, DbBotMark[]>();
  for (const m of marks) {
    const cur = latestMark.get(m.bot_id);
    if (!cur || m.t > cur.t) latestMark.set(m.bot_id, m);
    const list = marksByBot.get(m.bot_id) ?? [];
    list.push(m);
    marksByBot.set(m.bot_id, list);
  }
  for (const list of marksByBot.values()) {
    list.sort((a, b) => Number(a.t) - Number(b.t));
  }

  // Deduplicate trades in case multiple cycles recorded the same fill.
  const seenTrades = new Set<string>();
  const dedupedTrades: any[] = [];
  for (const t of trades) {
    const key = `${t.bot_id}:${t.ticker}:${t.t_sig}:${t.exit_t}`;
    if (seenTrades.has(key)) continue;
    seenTrades.add(key);
    dedupedTrades.push(t);
  }

  const tradesByBot = new Map<string, any[]>();
  for (const t of dedupedTrades) {
    const arr = tradesByBot.get(t.bot_id) ?? [];
    arr.push(t);
    tradesByBot.set(t.bot_id, arr);
  }
  for (const list of tradesByBot.values()) {
    list.sort((a, b) => Number(a.exit_t) - Number(b.exit_t));
  }

  const variants: Variant[] = bots.map((b) => {
    const m = latestMark.get(b.id);
    const botMarks = marksByBot.get(b.id) ?? [];
    const botTrades = tradesByBot.get(b.id) ?? [];
    const open = ((m?.open_json as any[]) ?? []).map((o: any) => {
      const side: "long" | "short" =
        o.side === 1 || o.side === "long" ? "long" : o.side === -1 || o.side === "short" ? "short" : (b.direction === "long" ? "long" : "short");
      const sign = side === "long" ? 1 : -1;
      const entry = Number(o.entry ?? 0);
      const notional = Number(o.notional ?? 0);
      const stop = Number(o.stop ?? 0);
      const sym = o.symbol || symbols[o.ticker] || (o.ticker ? `${o.ticker}USDT` : "");
      const livePx = o.px != null ? Number(o.px) : (sym && prices[sym] != null ? prices[sym] : null);
      const upct = o.upct != null ? Number(o.upct) : (livePx && entry ? sign * (livePx / entry - 1) : null);
      const upnl = o.upnl != null ? Number(o.upnl) : (upct != null && notional ? notional * upct : null);
      const room =
        o.room != null
          ? Number(o.room)
          : livePx && stop
            ? (sign === -1 ? (stop - livePx) / livePx : (livePx - stop) / livePx)
            : null;
      return {
        variant: b.name,
        ticker: o.ticker ?? "",
        side,
        entry,
        px: livePx,
        upct,
        upnl,
        stop,
        room,
        notional,
        t_sig: Number(o.t_sig ?? 0),
        tp: o.tp != null ? Number(o.tp) : null,
        exits_at: Number(o.exits_at ?? (o.t_sig && o.hold ? Number(o.t_sig) + Number(o.hold) * 900_000 : 0)),
      };
    }) as Position[];
    const equity = Number(m?.equity ?? START);
    const ret = (equity / START - 1) * 100;
    const closed = Math.max(m?.closed ?? 0, botTrades.length);
    const wins = botTrades.filter((t) => Number(t.pnl ?? t.net ?? 0) > 0).length;
    const win =
      m?.win != null
        ? Number(m.win)
        : botTrades.length
          ? Math.round((wins / botTrades.length) * 100)
          : null;
    const avg = botTrades.length
      ? (botTrades.reduce((a, t) => a + Number(t.net ?? 0), 0) / botTrades.length) * 100
      : null;

    // Equity curve from the per-cycle marks alone — one authoritative realized
    // equity series. (Previously this merged a trades-derived cumulative with
    // the marks and sorted them together; where the two disagreed the single
    // line ping-ponged between them, which is what made the chart sawtooth.)
    // botMarks is already sorted ascending by t.
    const curve: [number, number][] = botMarks.map(
      (mk) => [Number(mk.t), Number(mk.equity)] as [number, number],
    );
    // Anchor the line at the starting equity so it begins at $10k.
    if (curve.length === 0 || curve[0][1] !== START) {
      const launchMs = b.launched_at
        ? new Date(b.launched_at).getTime()
        : curve.length
          ? curve[0][0] - 900_000
          : Date.now();
      const anchorT = curve.length ? Math.min(launchMs, curve[0][0] - 60_000) : launchMs;
      curve.unshift([anchorT, START]);
    }

    return {
      name: b.name,
      group: (b.direction as any) ?? null,
      equity,
      ret,
      open,
      closed,
      win,
      avg,
      bt: b.bt,
      curve,
      kill: m?.kill ?? false,
      params: JSON.stringify(b.params ?? {}),
      note: b.note ?? null,
      cfg: b.params ?? null,
    };
  });
  const positions: Position[] = variants.flatMap((v) => v.open);
  const allTrades: Trade[] = dedupedTrades.map((t) => ({
    exit_t: Number(t.exit_t),
    variant: bots.find((b) => b.id === t.bot_id)?.name ?? t.bot_id,
    ticker: t.ticker,
    side: t.side === 1 || t.side === "long" ? "long" : t.side === -1 || t.side === "short" ? "short" : (t.side ?? "long"),
    kind: t.kind ?? "",
    net: Number(t.net ?? 0),
    pnl: Number(t.pnl ?? 0),
    notional: Number(t.notional ?? 0),
    t_sig: Number(t.t_sig),
    entry: Number(t.entry),
    stop: Number(t.stop ?? 0),
    equity_after: 0,
  } as Trade));
  return {
    now: Date.now(),
    start: START,
    gate: { bear: null },
    hero: { base_pnl: 0, base_ret: 0, base_closed: 0, base_avg: null, bench: 0,
            fleet_pnl: variants.reduce((a, v) => a + (v.equity - START), 0),
            unreal: positions.reduce((a, o) => a + (o.upnl || 0), 0),
            week_pnl: 0, closed: allTrades.length },
    variants,
    strats: {},
    positions,
    trades: allTrades,
    log: [],
    running: true,
    loaded: true,
    paused: false,
    health: { status: "green", msg: "" },
    ntfy: "",
    state_age_s: 0,
    symbols,
  };
}

export function useFleet(intervalMs = 10_000): FleetState {
  const [data, setData] = useState<Payload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dataRef = useRef<Payload | null>(null);
  const symbolsRef = useRef<Record<string, string>>({});

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const needCoins = Object.keys(symbolsRef.current).length === 0;
        const [{ data: bots }, { data: marks }, { data: trades }, coinsRes] = await Promise.all([
          supabase.from("pf_bots").select("*").eq("stage", "deployed"),
          supabase.from("pf_bot_marks").select("*").order("t", { ascending: false }).limit(2000),
          supabase.from("pf_bot_trades").select("*").order("exit_t", { ascending: false }).limit(1000),
          needCoins
            ? supabase.from("pf_coins").select("symbol,binance_symbol")
            : Promise.resolve({ data: null }),
        ]);
        if (!alive) return;
        if (coinsRes.data) {
          const map: Record<string, string> = {};
          for (const c of coinsRes.data as { symbol: string; binance_symbol: string }[]) {
            if (c.symbol && c.binance_symbol) map[c.symbol] = c.binance_symbol;
          }
          symbolsRef.current = map;
        }
        const hasOpen = ((marks as DbBotMark[]) ?? []).some(
          (m) => Array.isArray(m.open_json) && (m.open_json as unknown[]).length > 0,
        );
        let prices: Record<string, number> = {};
        if (hasOpen) {
          try {
            const pr = await fetch("https://fapi.binance.com/fapi/v1/ticker/price", { cache: "no-store" });
            if (pr.ok) {
              const rows: { symbol: string; price: string }[] = await pr.json();
              for (const r of rows) prices[r.symbol] = Number(r.price);
            }
          } catch {
            /* ignore price fetch failure */
          }
        }
        const p = buildPayload(
          (bots as DbBot[]) ?? [],
          (marks as DbBotMark[]) ?? [],
          trades ?? [],
          symbolsRef.current,
          prices,
        );
        dataRef.current = p;
        setData(p);
        setError(null);
      } catch (e) {
        if (!alive) return;
        if (!dataRef.current) setError((e as Error).message);
      } finally {
        if (alive) timer = setTimeout(tick, intervalMs);
      }
    };
    tick();
    return () => { alive = false; clearTimeout(timer); };
  }, [intervalMs]);

  return { data, error, loading: data === null && error === null };
}