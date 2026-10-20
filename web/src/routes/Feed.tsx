import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useData } from "../api/context";
import { ago, pct, usd } from "../lib/format";
import p from "./pages.module.css";
import s from "./feed.module.css";

type EvType = "exit" | "entry";
interface Ev {
  t: number;
  type: EvType;
  bot: string;
  ticker: string;
  side?: string;
  net?: number; // fraction
  pnl?: number; // dollars
  kind?: string;
}

// The feed is the home surface: a chronological stream of what the fleet's
// bots are doing right now, built from the same live payload the dashboard
// uses. (Entries + exits today; copies / follows / new-highs land once the
// event stream + social layer exist — see DESIGN.md.)
export default function Feed() {
  const d = useData();
  const nav = useNavigate();

  const events: Ev[] = useMemo(() => {
    const ev: Ev[] = [];
    for (const t of d.trades)
      ev.push({ t: t.exit_t, type: "exit", bot: t.variant, ticker: t.ticker,
                net: t.net, pnl: t.pnl, kind: t.kind });
    for (const pos of d.positions)
      ev.push({ t: pos.t_sig, type: "entry", bot: pos.variant,
                ticker: pos.ticker, side: pos.side });
    return ev.sort((a, b) => b.t - a.t).slice(0, 120);
  }, [d]);

  return (
    <>
      <div className={p.top}>
        <div>
          <h1 className={p.title}>Feed</h1>
          <div className={p.subtitle}>
            What your bots are doing, as it happens. {d.positions.length} open ·{" "}
            {d.hero.closed} trades closed.
          </div>
        </div>
      </div>

      <div className={p.body}>
        <div className={s.feed}>
          {events.map((e, i) => {
            const up = (e.net ?? 0) >= 0;
            return (
              <div key={i} className={s.row}>
                <span
                  className={`${s.dot} ${
                    e.type === "entry" ? s.dotEntry : up ? s.dotUp : s.dotDown
                  }`}
                />
                <button
                  className={s.bot}
                  onClick={() => nav(`/bot/${e.bot}`)}
                  title={`Open ${e.bot}`}
                >
                  {e.bot}
                </button>
                <span className={s.text}>
                  {e.type === "entry" ? (
                    <>
                      opened a {e.side} on <b>{e.ticker}</b>
                    </>
                  ) : (
                    <>
                      closed <b>{e.ticker}</b>
                      {e.kind ? <span className={s.kind}> · {e.kind}</span> : null}
                    </>
                  )}
                </span>
                {e.type === "exit" && e.net != null && (
                  <span className={`num ${up ? s.up : s.down}`}>
                    {pct(e.net * 100, true)}
                    {e.pnl != null && (
                      <span className={s.pnl}> {usd(e.pnl, true)}</span>
                    )}
                  </span>
                )}
                <span className={s.time}>{ago((d.now - e.t) / 1000)}</span>
              </div>
            );
          })}
          {events.length === 0 && (
            <div className="muted" style={{ padding: "40px 0" }}>
              No activity yet — the fleet will fill this as bots trade.
            </div>
          )}
        </div>
      </div>
    </>
  );
}
