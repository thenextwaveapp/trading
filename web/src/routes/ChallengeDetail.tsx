import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../auth";
import { enterChallenge, useChallenge, useChallengeBoard } from "../db/queries";
import type { DbBotCard, DbChallengeStanding } from "../db/types";
import { pct } from "../lib/format";
import { JUDGE_LABEL, holeSummary } from "./Challenges";
import p from "./pages.module.css";
import s from "./Challenges.module.css";

function fmtWhen(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

export default function ChallengeDetail() {
  const { slug } = useParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const { data: ch, loading } = useChallenge(slug ?? "");
  const { entries, standings, loading: boardLoading } = useChallengeBoard(ch?.id ?? null);
  const [entering, setEntering] = useState(false);

  const nameById = useMemo(() => {
    const m = new Map<string, DbBotCard>();
    for (const e of entries) m.set(e.id, e);
    return m;
  }, [entries]);

  if (loading) {
    return <div className="muted" style={{ padding: 40 }}>Loading challenge…</div>;
  }
  if (!ch) {
    return <div className="muted" style={{ padding: 40 }}>Challenge not found.</div>;
  }

  const handleEnter = async () => {
    if (!user) {
      nav("/signin");
      return;
    }
    setEntering(true);
    const { data } = await enterChallenge(ch, user.id);
    setEntering(false);
    if (data?.id) nav(`/build/compose?bot=${encodeURIComponent(data.id)}`);
  };

  const sealed = ch.seal && ch.status !== "closed";
  const canEnter = ch.status === "open";
  const nameOf = (st: DbChallengeStanding) =>
    nameById.get(st.bot_id)?.name ?? "Hidden entry";

  const placed = standings.filter((x) => x.place != null);
  const unplaced = standings.filter((x) => x.place == null);
  const top = placed.slice(0, 3);

  return (
    <>
      <div className={p.crumb}>
        <span className={p.crumbLink} onClick={() => nav("/challenges")}>← Challenges</span>
      </div>

      <div className={p.top}>
        <div>
          <h1 className={p.title}>{ch.title}</h1>
          {ch.blurb && <div className={p.subtitle}>{ch.blurb}</div>}
          <div className={s.meta} style={{ marginTop: 12 }}>
            <span>Tune <span className={s.hole}>{holeSummary(ch)}</span></span>
            <span>Judge · {JUDGE_LABEL[ch.judge] ?? ch.judge}</span>
            <span>Build closes {fmtWhen(ch.build_close)}</span>
            <span>Market {fmtWhen(ch.market_open)} → {fmtWhen(ch.market_close)}</span>
          </div>
        </div>
        {canEnter && (
          <button
            className={`${p.btn} ${p.pri}`}
            disabled={entering}
            onClick={() => void handleEnter()}
          >
            {entering ? "Entering…" : "Enter challenge"}
          </button>
        )}
      </div>

      <div className={p.body}>
        {boardLoading ? (
          <div className="muted" style={{ padding: "40px 0" }}>Loading board…</div>
        ) : placed.length > 0 ? (
          <>
            <div className={s.podium}>
              {top.map((st, i) => {
                const up = (st.total_return ?? 0) >= 0;
                return (
                  <div key={st.id} className={`card ${s.pCard}`}>
                    <div className="num gradtext" style={{ fontSize: 30, opacity: 0.8 }}>#{i + 1}</div>
                    <div
                      className="lk"
                      style={{ fontSize: 16, fontWeight: 500, marginTop: 6 }}
                      onClick={() => nav("/bot/" + encodeURIComponent(nameOf(st)))}
                    >
                      {nameOf(st)}
                    </div>
                    <div className={`num ${up ? "up" : "down"}`} style={{ fontSize: 26, marginTop: 8 }}>
                      {pct(st.total_return ?? 0, true)}
                    </div>
                    <div className="lbl num" style={{ marginTop: 4 }}>
                      {st.trades ?? 0} trades · max DD {pct((st.max_drawdown ?? 0) * 100, false)}
                    </div>
                  </div>
                );
              })}
            </div>

            <div className={s.tableWrap}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th>#</th>
                    <th className={s.left}>Entry</th>
                    <th>Score</th>
                    <th>Return</th>
                    <th>Max DD</th>
                    <th>Trades</th>
                  </tr>
                </thead>
                <tbody>
                  {placed.map((st) => {
                    const up = (st.total_return ?? 0) >= 0;
                    const mine = user && nameById.get(st.bot_id)?.owner === user.id;
                    return (
                      <tr key={st.id} className={mine ? s.me : ""}>
                        <td className="num">{st.place}</td>
                        <td className={s.left}>
                          <span className="lk" onClick={() => nav("/bot/" + encodeURIComponent(nameOf(st)))}>
                            {nameOf(st)}
                          </span>
                        </td>
                        <td className="num muted">{st.score == null ? "–" : st.score.toFixed(2)}</td>
                        <td className={`num ${up ? "up" : "down"}`}>{pct(st.total_return ?? 0, true)}</td>
                        <td className="num muted">{pct((st.max_drawdown ?? 0) * 100, false)}</td>
                        <td className="num muted">{st.trades ?? 0}</td>
                      </tr>
                    );
                  })}
                  {unplaced.map((st) => (
                    <tr key={st.id} style={{ opacity: 0.5 }}>
                      <td className="num">–</td>
                      <td className={s.left}>{nameOf(st)}</td>
                      <td className="num muted" colSpan={4}>ineligible</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <>
            {sealed && (
              <div className={s.sealNote}>
                {entries.length} {entries.length === 1 ? "entry" : "entries"} ·
                {" "}Setups are sealed until the market window closes — records show, recipes don't.
              </div>
            )}
            {entries.length === 0 ? (
              <div className="muted" style={{ padding: "40px 0" }}>
                No entries yet.{canEnter ? " Be the first — enter above." : ""}
              </div>
            ) : (
              <div className={s.grid}>
                {entries.map((e) => (
                  <div key={e.id} className={`card ${s.chCard}`}>
                    <div className={s.chTitle}>{e.name}</div>
                    <div className="lbl">
                      {e.stage === "deployed" ? "Battling" : e.stage}
                      {e.bt != null ? ` · ${pct(e.bt, true)}` : ""}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
