import { useEffect, useRef, useState } from "react";
import { GitFork, Heart, MessageCircle, Share2 } from "lucide-react";
import { fetchCandles } from "../api/client";
import { botColor } from "../lib/brand";
import { held, identicon, pct, px, usd } from "../lib/format";
import { botPath, tradePath } from "../lib/paths";
import { useData } from "../api/context";
import type { DbBot, DbEvent } from "../db/types";
import type { Bot, Trade } from "../api/types";
import Spark from "./Spark";
import s from "./FeedRow.module.css";

/** stable pseudo-count from an id, so mock engagement numbers don't flicker on
 *  re-render (no Math.random). */
function hashNum(str: string, mod: number): number {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0;
  return h % mod;
}

/** Mock social actions for a feed card. Like toggles locally; the rest are
 *  placeholders. Copy is the trading-native one — clone the bot into your
 *  fleet. Stops propagation so taps don't open the card. */
function SocialBar({ e }: { e: DbEvent }) {
  const [liked, setLiked] = useState(false);
  const likes = hashNum(e.id + "l", 240) + (liked ? 1 : 0);
  const comments = hashNum(e.id + "c", 36);
  const stop = (fn?: () => void) => (ev: React.MouseEvent) => {
    ev.stopPropagation();
    fn?.();
  };
  return (
    <div className={s.actions} onClick={(ev) => ev.stopPropagation()}>
      <button className={s.act} onClick={stop()} aria-label="Share">
        <Share2 size={16} strokeWidth={1.6} />
      </button>
      <button className={s.act} onClick={stop()} aria-label="Comment">
        <MessageCircle size={16} strokeWidth={1.6} />
        <span className="num">{comments}</span>
      </button>
      <button className={`${s.act} ${liked ? s.liked : ""}`} onClick={stop(() => setLiked((v) => !v))} aria-pressed={liked}>
        <Heart size={16} strokeWidth={1.6} fill={liked ? "currentColor" : "none"} />
        <span className="num">{likes}</span>
      </button>
      {/* the app's signature accent copy-a-bot action, not a muted icon */}
      <button className={`copyBtn ${s.actCopy}`} onClick={stop()}>
        <GitFork size={14} strokeWidth={1.75} />
        Copy
      </button>
    </div>
  );
}

function rel(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "now";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

function Dot({ seed, color, size = 30 }: { seed: string; color: string; size?: number }) {
  const inner = Math.round(size * 0.62);
  const off = Math.round((size - inner) / 2);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flex: "none" }}>
      <rect width={size} height={size} rx={size / 2} fill="#12161D" />
      <path d={identicon(seed, inner)} fill={color} transform={`translate(${off} ${off})`} />
    </svg>
  );
}

/** Real entry→exit price path for a closed trade, pulled from candle history.
 *  Fetched only when the card scrolls into view, and cached module-wide so the
 *  same trade never fetches twice (feeds re-render a lot). */
const SPARK_CACHE = new Map<string, number[]>();
const SPARK_INFLIGHT = new Map<string, Promise<number[]>>();

function pickInterval(ms: number): string {
  if (ms <= 8 * 3_600_000) return "15m"; // intraday
  if (ms <= 4 * 86_400_000) return "1h"; // a few days
  if (ms <= 30 * 86_400_000) return "4h"; // weeks
  return "1d";
}

function useTradeSpark(enabled: boolean, symbol: string, market: string | undefined, start: number, end: number) {
  const ref = useRef<HTMLDivElement>(null);
  const [pts, setPts] = useState<number[] | null>(null);
  const key = enabled && symbol && end > start ? `${symbol}|${start}|${end}` : "";

  useEffect(() => {
    if (!key) return;
    const cached = SPARK_CACHE.get(key);
    if (cached) { setPts(cached); return; }
    const el = ref.current;
    if (!el) return;
    const [sym, sStr, eStr] = key.split("|");
    const t0 = Number(sStr), t1 = Number(eStr);
    let cancelled = false;
    const run = async () => {
      const pad = (t1 - t0) * 0.04; // let entry/exit sit inside the window
      let prom = SPARK_INFLIGHT.get(key);
      if (!prom) {
        prom = fetchCandles({ symbol: sym, market, interval: pickInterval(t1 - t0), start: Math.floor(t0 - pad), end: Math.ceil(t1 + pad), limit: 300 })
          .then((ks) => ks.map((c) => c.c))
          .catch(() => []);
        SPARK_INFLIGHT.set(key, prom);
      }
      const closes = await prom;
      SPARK_INFLIGHT.delete(key);
      if (closes.length >= 2) SPARK_CACHE.set(key, closes);
      if (!cancelled) setPts(closes.length >= 2 ? closes : null);
    };
    const io = new IntersectionObserver(
      (entries) => { if (entries.some((x) => x.isIntersecting)) { io.disconnect(); void run(); } },
      { rootMargin: "200px" },
    );
    io.observe(el);
    return () => { cancelled = true; io.disconnect(); };
  }, [key, market]);

  return [ref, pts] as const;
}

function Stat({ k, v, cls, big }: { k: string; v: string; cls?: string; big?: boolean }) {
  return (
    <div className={s.stat}>
      <div className={s.sk}>{k}</div>
      <div className={`num ${big ? s.svBig : s.sv} ${cls ?? ""}`}>{v}</div>
    </div>
  );
}

/** One activity card — a trade ticket or a social one-liner, glass like the
 *  rest of the app. Clicking a trade goes to the trade's own page. */
export default function FeedRow({ e, bot, live, onOpen }: {
  e: DbEvent; bot?: DbBot; live?: Bot; onOpen: (path: string) => void;
}) {
  const data = useData();
  const pay = e.payload ?? {};
  const name = e.bot_name ?? (e.actor_handle ? "@" + e.actor_handle : "Someone");
  const color = bot ? botColor(bot) : "#5e8fd8";
  const builderHandle = bot?.builder?.handle ?? e.actor_handle ?? null;

  // Trade events carry a ticker; an exit resolves to the closed trade behind it.
  // Resolved up here (before the social early-return) so the spark hook can run
  // unconditionally — React requires hooks on every render path.
  const ticker = e.type === "entered" || e.type === "exited" ? String(pay.ticker ?? "") : "";
  const entered = e.type === "entered";
  let tr: Trade | undefined;
  if (e.type === "exited") {
    const ts = new Date(e.ts).getTime();
    tr = (data.trades ?? [])
      .filter((t) => t.bot === name && t.ticker === ticker)
      .sort((a, b) => Math.abs(a.exit_t - ts) - Math.abs(b.exit_t - ts))[0];
  }
  const sparkMarket = bot?.market ?? undefined;
  const sparkSym = ticker
    ? data.symbols[ticker] || (sparkMarket && sparkMarket !== "crypto" ? ticker : ticker.endsWith("USDT") ? ticker : ticker + "USDT")
    : "";
  const [sparkRef, sparkPts] = useTradeSpark(!!tr, sparkSym, sparkMarket, tr?.t_sig ?? 0, tr?.exit_t ?? 0);

  // head row: avatar · "<name> <headline…>" · time. The headline rides the
  // name line, so even a one-line social card tells the whole story.
  const head = (headline: React.ReactNode) => (
    <div className={s.head}>
      <Dot
        seed={e.bot_name ? name : e.actor_handle ? "@" + e.actor_handle : name}
        color={e.type === "kill_switch" ? "#ff5c6c" : color}
      />
      <div className={s.who}>
        <div className={s.line}>
          <span className={s.name}>{name}</span>
          {headline}
        </div>
        {builderHandle && e.bot_name && <div className={s.sub}>@{builderHandle}</div>}
      </div>
      <span className={s.time}>{rel(e.ts)}</span>
    </div>
  );

  // ---- social (non-trade) events: one line is the whole card ----
  if (e.type !== "entered" && e.type !== "exited") {
    // "copied": the subject decides the voice — a bot is "copied from" its
    // source; a builder (no bot on the event) "copied" it
    const verb =
      e.type === "followed" ? "followed a builder"
        : e.type === "copied" ? (
          e.bot_name
            ? <>copied from <b>{String(pay.from_bot_name ?? "another bot")}</b></>
            : <>copied <b>{String(pay.from_bot_name ?? "a bot")}</b></>
        )
          : e.type === "kill_switch" ? "tripped its loss limit — paused" : e.type;
    const clickable = !!e.bot_name;
    return (
      <div
        className={`${s.c} ${s.social} ${e.type === "kill_switch" ? s.danger : ""} ${clickable ? s.click : ""}`}
        onClick={() => e.bot_name && onOpen(bot ? botPath(bot) : "/bot/" + encodeURIComponent(e.bot_name))}
      >
        {head(<span className={`${s.hl} ${e.type === "kill_switch" ? s.hlDanger : ""}`}>{verb}</span>)}
      </div>
    );
  }

  // ---- trade events ----
  const side = (pay.side as string) ?? bot?.direction ?? null;
  const openPos = live?.open?.find((o) => o.ticker === ticker);

  const net = typeof pay.net === "number" ? pay.net * 100 : tr ? tr.net * 100 : null;
  const unreal = openPos?.upct != null ? openPos.upct * 100 : null;
  const shownPct = entered ? unreal : net;
  const up = (shownPct ?? 0) >= 0;

  const entryPx = entered ? (openPos?.entry ?? (pay.entry != null ? Number(pay.entry) : null)) : tr?.entry ?? null;
  const exitPx = !entered && tr
    ? (tr.side === "short" ? tr.entry * (1 - tr.net) : tr.entry * (1 + tr.net))
    : null;
  const curPx = entered ? openPos?.px ?? null : null;
  const pnl = entered
    ? openPos?.upnl ?? null
    : typeof pay.pnl === "number" ? pay.pnl : tr?.pnl ?? null;
  const heldStr = entered
    ? openPos?.t_sig ? held(Date.now() - openPos.t_sig) : null
    : tr ? held(tr.exit_t - tr.t_sig) : null;

  // the trade's own page; stamp the event time so it finds the right trade
  const tradeHref = e.bot_name
    ? tradePath(bot ?? { name }, ticker, new Date(e.ts).getTime())
    : null;

  return (
    <div
      className={`${s.c} ${s.click}`}
      style={{ "--bot": color } as React.CSSProperties}
      onClick={() => tradeHref && onOpen(tradeHref)}
    >
      {head(
        <>
          <span className={s.hl}>{entered ? "opened" : "exited"}</span>
          <span className={s.tkr}>{ticker}</span>
          {side && <span className={`${s.tag} ${side === "short" ? s.short : s.long}`}>{side.toUpperCase()}</span>}
          <span className={`${s.tag} ${entered ? s.open : s.mut}`}>{entered ? "OPEN" : "CLOSED"}</span>
        </>,
      )}
      <div className={s.stats}>
        {/* primary column: the headline % with P&L stacked beneath it */}
        <div className={s.lead}>
          {shownPct == null && entryPx != null ? (
            <Stat k="ENTRY" v={px(entryPx)} big />
          ) : (
            <Stat
              k={entered ? "UNREALIZED" : "NET"}
              v={shownPct == null ? "–" : pct(shownPct, true)}
              cls={shownPct == null ? "muted" : up ? "up" : "down"}
              big
            />
          )}
          {pnl != null && <Stat k="P&L" v={usd(pnl, true)} cls={pnl >= 0 ? "up" : "down"} />}
        </div>
        {entryPx != null && shownPct != null && <Stat k="ENTRY" v={px(entryPx)} />}
        {curPx != null && <Stat k="PRICE" v={px(curPx)} />}
        {exitPx != null && <Stat k="EXIT" v={px(exitPx)} />}
        {heldStr && <Stat k="HELD" v={heldStr} />}
        {/* the closed trade's real price path (entry→exit window), fetched from
            candles when the card scrolls in; coloured by whether it won */}
        {!entered && tr && (
          <div className={s.spark} ref={sparkRef}>
            {sparkPts && <Spark data={sparkPts} w={116} h={34} up={up} area />}
          </div>
        )}
      </div>
      <SocialBar e={e} />
    </div>
  );
}
