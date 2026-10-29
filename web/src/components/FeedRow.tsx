import { botColor } from "../lib/brand";
import { identicon, pct } from "../lib/format";
import { useData } from "../api/context";
import { useCandle, type CandleReq } from "./CandleModal";
import type { DbBot, DbEvent } from "../db/types";
import type { Variant } from "../api/types";
import s from "./FeedRow.module.css";

function rel(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "now";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

function Dot({ seed, color, size = 34 }: { seed: string; color: string; size?: number }) {
  const inner = Math.round(size * 0.62);
  const off = Math.round((size - inner) / 2);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flex: "none" }}>
      <rect width={size} height={size} rx={size / 2} fill="#12161D" />
      <path d={identicon(seed, inner)} fill={color} transform={`translate(${off} ${off})`} />
    </svg>
  );
}

/** One activity line — a trade or a social event — styled like a market-table row.
 *  Clicking a trade opens the candle modal zoomed to that trade with entry/exit/SL/TP. */
export default function FeedRow({ e, bot, variant, onOpen }: {
  e: DbEvent; bot?: DbBot; variant?: Variant; onOpen: (path: string) => void;
}) {
  const data = useData();
  const openCandle = useCandle();
  const pay = e.payload ?? {};
  const name = e.bot_name ?? (e.actor_handle ? "@" + e.actor_handle : "Someone");
  const color = bot ? botColor(bot) : "#5e8fd8";
  const builderHandle = bot?.builder?.handle ?? e.actor_handle ?? null;

  // social (non-trade) events — click goes to the bot profile when there is one
  if (e.type !== "entered" && e.type !== "exited") {
    const verb =
      e.type === "followed" ? "followed a builder"
        : e.type === "copied" ? `copied ${String(pay.from_bot_name ?? "a bot")}`
          : e.type === "kill_switch" ? "tripped its loss limit" : e.type;
    const dotColor = e.type === "kill_switch" ? "#ff5c6c" : "#3ddc97";
    const clickable = !!e.bot_name;
    return (
      <div
        className={`${s.row} ${clickable ? s.click : ""}`}
        onClick={() => e.bot_name && onOpen("/bot/" + encodeURIComponent(e.bot_name))}
      >
        <Dot seed={e.actor_handle ? "@" + e.actor_handle : name} color={dotColor} />
        <div className={s.main}>
          <div className={s.line}><b>{name}</b> <span className={s.verb}>{verb}</span></div>
          {builderHandle && e.bot_name && <div className={s.sub}>@{builderHandle}</div>}
        </div>
        <span className={s.time} style={{ marginLeft: "auto" }}>{rel(e.ts)}</span>
      </div>
    );
  }

  // trade events
  const ticker = String(pay.ticker ?? "");
  const entered = e.type === "entered";
  const side = (pay.side as string) ?? bot?.direction ?? null;
  const openPos = variant?.open?.find((o) => o.ticker === ticker);
  const unreal = openPos?.upct != null ? openPos.upct * 100 : null;
  const net = typeof pay.net === "number" ? pay.net * 100 : null;
  const shownPct = entered ? unreal : net;
  const up = (shownPct ?? 0) >= 0;

  // Resolve the full trade (open position or closed trade) so the modal can zoom
  // to the right window and label entry/exit/SL/TP.
  const goto = e.bot_name ? "/bot/" + encodeURIComponent(e.bot_name) : undefined;
  const buildReq = (): CandleReq | null => {
    if (!ticker) return null;
    const sym = data.symbols[ticker] || (ticker.endsWith("USDT") ? ticker : `${ticker}USDT`);
    if (openPos) {
      return {
        sym, title: `${ticker} · ${name} (open)`, goto,
        t_sig: openPos.t_sig, entry: openPos.entry, stop: openPos.stop, tp: openPos.tp,
        exit_t: null, side: openPos.side,
      };
    }
    const ts = new Date(e.ts).getTime();
    const tr = (data.trades ?? [])
      .filter((t) => t.variant === name && t.ticker === ticker)
      .sort((a, b) => Math.abs(a.exit_t - ts) - Math.abs(b.exit_t - ts))[0];
    if (tr) {
      const exitPx = tr.side === "short" ? tr.entry * (1 - tr.net) : tr.entry * (1 + tr.net);
      return {
        sym, title: `${ticker} · ${name} (closed · ${tr.kind})`, goto,
        t_sig: tr.t_sig, entry: tr.entry, stop: tr.stop, tp: null, exit: exitPx,
        exit_t: tr.exit_t, kind: tr.kind, side: tr.side ?? side,
      };
    }
    if (pay.entry != null) {
      return { sym, title: `${ticker} · ${name}`, goto, t_sig: ts, entry: Number(pay.entry), side };
    }
    return null;
  };

  const open = () => {
    const req = buildReq();
    if (req) openCandle(req);
    else if (e.bot_name) onOpen("/bot/" + encodeURIComponent(e.bot_name));
  };

  return (
    <div className={`${s.row} ${s.click}`} onClick={open}>
      <Dot seed={name} color={color} />
      <div className={s.main}>
        <div className={s.line}>
          <b>{name}</b>
          <span className={s.verb}>{entered ? "opened" : "exited"} {ticker}</span>
          {side && <span className={`${s.side} ${side === "short" ? s.short : s.long}`}>{side.toUpperCase()}</span>}
        </div>
        {builderHandle && <div className={s.sub}>@{builderHandle}</div>}
      </div>
      <div className={s.right}>
        <span className={`num ${s.pnl} ${shownPct == null ? "muted" : up ? "up" : "down"}`}>
          {shownPct == null ? "—" : pct(shownPct, true)}
        </span>
        <span className={s.time}>{rel(e.ts)}</span>
      </div>
    </div>
  );
}
