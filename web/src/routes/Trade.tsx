import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useData } from "../api/context";
import { useBots, useMarketRow } from "../db/queries";
import { botColor } from "../lib/brand";
import { BotAvatar } from "../components/Avatar";
import { BackBar } from "../components/cells";
import Segmented from "../components/Segmented";
import { CANDLE_IVS, TradeCandles, type CandleReq } from "../components/CandleModal";
import { held, pct, px, usd } from "../lib/format";
import { botPath, botSlugOf, builderPath } from "../lib/paths";
import { useIsPhone } from "../lib/responsive";
import p from "./pages.module.css";
import s from "./Trade.module.css";

/** A single trade's own page: the zoomed chart with entry/exit/SL/TP, and the
 *  trade's vitals at full size. Route: /trade/:bot/:ticker/:t?  (t = event ms,
 *  used to pick the right closed trade when a bot traded the symbol often). */
export default function Trade() {
  // legacy /trade/:bot/:ticker/:t, or canonical /@handle/:botSlug/:ticker/:t
  const { bot: legacyName, handle: hParam, botSlug, ticker = "", t } = useParams();
  const ts = t ? Number(t) : null;
  const nav = useNavigate();
  const data = useData();
  const isPhone = useIsPhone();
  const { data: allBots } = useBots();
  const [iv, setIv] = useState("15m");

  const dbBot = useMemo(
    () =>
      legacyName
        ? (allBots ?? []).find((b) => b.name === legacyName)
        : hParam?.startsWith("@") && botSlug
          ? (allBots ?? []).find(
              (b) => b.builder?.handle === hParam.slice(1) && botSlugOf(b) === botSlug,
            )
          : undefined,
    [allBots, legacyName, hParam, botSlug],
  );
  const botName = dbBot?.name ?? legacyName ?? "";
  const live = useMemo(() => data.bots.find((v) => v.name === botName), [data.bots, botName]);
  const openPos = live?.open?.find((o) => o.ticker === ticker);

  // the closed trade nearest the event timestamp (bots re-trade symbols)
  const tr = useMemo(() => {
    const xs = (data.trades ?? []).filter((x) => x.bot === botName && x.ticker === ticker);
    if (!xs.length) return undefined;
    if (ts) return xs.slice().sort((a, b) => Math.abs(a.exit_t - ts) - Math.abs(b.exit_t - ts))[0];
    return xs.slice().sort((a, b) => b.exit_t - a.exit_t)[0];
  }, [data.trades, botName, ticker, ts]);

  // an event stamped after the last exit is the open position; otherwise the
  // nearest closed trade wins
  const isOpen = !!openPos && (!tr || !ts || ts > tr.exit_t + 60_000);

  const color = dbBot ? botColor(dbBot) : "#5e8fd8";
  const sym = data.symbols[ticker] || (ticker.endsWith("USDT") ? ticker : `${ticker}USDT`);
  const { data: mkt } = useMarketRow(sym);

  const req: CandleReq | null = useMemo(() => {
    if (!ticker) return null;
    if (isOpen && openPos) {
      return {
        sym, title: `${ticker} · ${botName} (open)`,
        t_sig: openPos.t_sig, entry: openPos.entry, stop: openPos.stop, tp: openPos.tp,
        exit_t: null, side: openPos.side,
      };
    }
    if (tr) {
      const exitPx = tr.side === "short" ? tr.entry * (1 - tr.net) : tr.entry * (1 + tr.net);
      return {
        sym, title: `${ticker} · ${botName} (closed)`,
        t_sig: tr.t_sig, entry: tr.entry, stop: tr.stop, tp: null, exit: exitPx,
        exit_t: tr.exit_t, kind: tr.kind, side: tr.side ?? null,
      };
    }
    return null;
  }, [isOpen, openPos, tr, sym, ticker, botName]);

  const side = isOpen ? openPos?.side : tr?.side;
  const shownPct = isOpen
    ? openPos?.upct != null ? openPos.upct * 100 : null
    : tr ? tr.net * 100 : null;
  const pnl = isOpen ? openPos?.upnl ?? null : tr?.pnl ?? null;
  const heldStr = isOpen
    ? openPos?.t_sig ? held(Date.now() - openPos.t_sig) : null
    : tr ? held(tr.exit_t - tr.t_sig) : null;
  const entryPx = isOpen ? openPos?.entry ?? null : tr?.entry ?? null;
  const exitPx = !isOpen && tr
    ? (tr.side === "short" ? tr.entry * (1 - tr.net) : tr.entry * (1 + tr.net))
    : null;
  const curPx = isOpen ? openPos?.px ?? null : null;
  const up = (shownPct ?? 0) >= 0;

  return (
    <>
      {!isPhone && <BackBar fallbackPath="/feed" fallbackLabel="Feed" />}
      <div className={`${p.shell} ${p.body}`} style={{ paddingTop: isPhone ? 14 : 10 }}>
        <div className={s.head}>
          {isPhone && <BackBar bare fallbackPath="/feed" fallbackLabel="Feed" />}
          <BotAvatar seed={botName} color={color} size={42} />
          <div className={s.names}>
            <div className={s.title}>
              <span className="lk" onClick={() => nav(dbBot ? botPath(dbBot) : "/bot/" + encodeURIComponent(botName))}>{botName}</span>
              <span className={s.sep}>·</span>
              {mkt?.logo && <img src={mkt.logo} alt="" width={18} height={18} className={s.instrumentLogo} />}
              <span className={s.tkr}>{ticker}</span>
              {side && <span className={`${s.tag} ${side === "short" ? s.short : s.long}`}>{side.toUpperCase()}</span>}
              <span className={`${s.tag} ${isOpen ? s.openTag : s.mut}`}>{isOpen ? "OPEN" : "CLOSED"}</span>
            </div>
            {(mkt?.name || dbBot?.builder?.handle) && (
              <div className={s.sub}>
                {mkt?.name && <span className={s.instrumentName}>{mkt.name}</span>}
                {mkt?.name && dbBot?.builder?.handle && <span className={s.sep}> · </span>}
                {dbBot?.builder?.handle && (
                  <>by <span className="lk" onClick={() => nav(builderPath(dbBot.builder!.handle))}>@{dbBot.builder.handle}</span></>
                )}
              </div>
            )}
          </div>
          <div className={s.actions}>
            <Segmented
              ariaLabel="Candle interval"
              size="sm"
              value={iv}
              onChange={setIv}
              options={CANDLE_IVS.map((k) => ({ value: k, label: k }))}
            />
            <button className={s.mkt} onClick={() => nav("/market/" + encodeURIComponent(sym))}>Market ↗</button>
          </div>
        </div>

        {req ? (
          <>
            <section className={p.statgrid} style={{ gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", marginBottom: 20 }}>
              <div className={p.statcell}>
                <div className="lbl">{isOpen ? "Unrealized" : "Net"}</div>
                <div className={`num ${p.statBig} ${shownPct == null ? "muted" : up ? "up" : "down"}`}>
                  {shownPct == null ? "–" : pct(shownPct, true)}
                </div>
              </div>
              <div className={p.statcell}>
                <div className="lbl">Entry</div>
                <div className={`num ${p.statBig}`}>{px(entryPx)}</div>
              </div>
              <div className={p.statcell}>
                <div className="lbl">{isOpen ? "Price now" : "Exit"}</div>
                <div className={`num ${p.statBig}`}>{px(isOpen ? curPx : exitPx)}</div>
              </div>
              <div className={p.statcell}>
                <div className="lbl">Held</div>
                <div className={`num ${p.statBig}`}>{heldStr ?? "–"}</div>
              </div>
              <div className={p.statcell}>
                <div className="lbl">P&L</div>
                <div className={`num ${p.statBig} ${pnl == null ? "" : pnl >= 0 ? "up" : "down"}`}>
                  {pnl == null ? "–" : usd(pnl, true)}
                </div>
              </div>
            </section>

            <div className={`card ${s.chartCard}`}>
              <TradeCandles req={req} iv={iv} className={s.chart} />
            </div>
          </>
        ) : (
          <div className="muted" style={{ padding: "40px 0" }}>
            No trade found for {botName} on {ticker}.
          </div>
        )}
      </div>
    </>
  );
}
