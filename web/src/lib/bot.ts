import { botColor } from "./brand";
import type { Bot } from "../api/types";
import type { DbBacktest, DbBot } from "../db/types";
import { START } from "./format";

/** Build the live-feed Bot shape from a bot's DB row (and latest backtest) for
 *  when the live engine feed doesn't include it — the pages still render, just
 *  without live positions/trades. */
export function botFromRow(bot: DbBot, bt?: DbBacktest | null): Bot {
  const equity = bt?.final_value ?? START;
  // Stored curves from older runs can be out of order; charts require
  // chronological time. Sort here so every fallback render is safe.
  const curve = [...(bt?.equity_curve ?? [])].sort((a, b) => a[0] - b[0]);
  return {
    name: bot.name,
    params: JSON.stringify(bot.params ?? {}),
    equity,
    ret: (equity / START - 1) * 100,
    open: [],
    closed: bt?.trades ?? 0,
    win: bt?.win_rate != null ? Math.round(bt.win_rate * 1000) / 10 : null,
    avg: bt?.net_per_trade ?? null,
    bt: bot.bt,
    curve,
    kill: false,
    group: bot.direction,
    note: bot.note,
    cfg: bot.params ?? null,
    color: botColor(bot),
  };
}
