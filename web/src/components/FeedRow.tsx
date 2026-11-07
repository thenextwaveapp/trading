import { botColor } from "../lib/brand";
import { held, identicon, pct, px, usd } from "../lib/format";
import { botPath, tradePath } from "../lib/paths";
import { useData } from "../api/context";
import type { DbBot, DbEvent } from "../db/types";
import type { Bot, Trade } from "../api/types";
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
        className={`card ${s.c} ${s.social} ${e.type === "kill_switch" ? s.danger : ""} ${clickable ? s.click : ""}`}
        onClick={() => e.bot_name && onOpen(bot ? botPath(bot) : "/bot/" + encodeURIComponent(e.bot_name))}
      >
        {head(<span className={`${s.hl} ${e.type === "kill_switch" ? s.hlDanger : ""}`}>{verb}</span>)}
      </div>
    );
  }

  // ---- trade events ----
  const ticker = String(pay.ticker ?? "");
  const entered = e.type === "entered";
  const side = (pay.side as string) ?? bot?.direction ?? null;
  const openPos = live?.open?.find((o) => o.ticker === ticker);

  // the closed trade behind an exit event — carries entry/timing/pnl
  let tr: Trade | undefined;
  if (!entered) {
    const ts = new Date(e.ts).getTime();
    tr = (data.trades ?? [])
      .filter((t) => t.bot === name && t.ticker === ticker)
      .sort((a, b) => Math.abs(a.exit_t - ts) - Math.abs(b.exit_t - ts))[0];
  }

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
      className={`card ${s.c} ${s.click}`}
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
        {entryPx != null && shownPct != null && <Stat k="ENTRY" v={px(entryPx)} />}
        {curPx != null && <Stat k="PRICE" v={px(curPx)} />}
        {exitPx != null && <Stat k="EXIT" v={px(exitPx)} />}
        {heldStr && <Stat k="HELD" v={heldStr} />}
        {pnl != null && <Stat k="P&L" v={usd(pnl, true)} cls={pnl >= 0 ? "up" : "down"} />}
      </div>
    </div>
  );
}
