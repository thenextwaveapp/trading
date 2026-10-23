import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useCurrentHandle } from "../auth";
import { useData } from "../api/context";
import { useBots, useProfile } from "../db/queries";
import { DIRLBL, identicon, pct, windowReturn } from "../lib/format";
import p from "./pages.module.css";
import s from "./Builder.module.css";

export default function Builder() {
  const nav = useNavigate();
  // A :handle in the URL shows that builder; otherwise the signed-in user.
  const { handle: param } = useParams();
  const me = useCurrentHandle();
  const handle = param ?? me ?? null;
  const live = useData();
  const { data: profile } = useProfile(handle ?? "");
  const { data: allBots } = useBots();

  const mine = useMemo(() => (allBots ?? []).filter((b) => b.builder?.handle === handle), [allBots, handle]);
  const byName = useMemo(() => new Map(live.variants.map((v) => [v.name, v])), [live.variants]);

  const bots = mine
    .map((b) => ({ b, v: byName.get(b.name) }))
    .filter((x) => x.v)
    .map((x) => ({ ...x, ret: windowReturn(x.v!.curve, 30, live.now) }));

  const liveBots = bots.filter((x) => x.b.stage === "deployed");
  const totalTrades = bots.reduce((a, x) => a + (x.v?.closed ?? 0), 0);

  // Logged out with no :handle — nobody to show.
  if (!handle) {
    return (
      <div className={p.body} style={{ padding: 24 }}>
        <div className="muted">Sign in to see your builder profile.</div>
        <button className={`${p.btn} ${p.sm}`} style={{ marginTop: 12 }} onClick={() => nav("/signin")}>
          Sign in
        </button>
      </div>
    );
  }

  return (
    <>
      <div className={p.crumb}>
        <span className="lk" onClick={() => nav("/leaderboard")}>Leaderboard</span> / <b>@{handle}</b>
      </div>

      <div className={p.body}>
        <section className={s.hero}>
          <svg width="112" height="112" viewBox="0 0 112 112">
            <rect width="112" height="112" rx="28" fill="#12161D" />
            <path d={identicon("@" + handle, 64)} fill={profile?.avatar_color || "#3a81d7"} transform="translate(24 24)" />
          </svg>
          <div className={s.heroMain}>
            <h1 className={s.h1}>@{handle}</h1>
            {profile?.bio && <div className={s.quote}>{profile.bio}</div>}
            <div className={s.chips}>
              <span className="chip">{liveBots.length} bots live</span>
              <span className="chip">{totalTrades} trades</span>
            </div>
          </div>
        </section>

        <section className={p.statgrid} style={{ gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))" }}>
          <Stat label="Bots live now" value={String(liveBots.length)} />
          <Stat label="Public & shared" value={String(bots.length)} />
          <Stat label="Total trades" value={totalTrades.toLocaleString()} />
          <Stat label="Avg win rate" value={avgWin(bots.map((x) => x.v?.win ?? null))} />
        </section>

        <div className={p.sectionHead}><h2 className={p.h2}>Bots</h2></div>
        {bots.length === 0 ? (
          <div className="muted" style={{ padding: "8px 0" }}>No public bots.</div>
        ) : (
          <div className={s.grid}>
            {bots.map(({ b, ret }) => {
              const up = ret >= 0;
              return (
                <div key={b.id} className={`card ${s.bc}`}>
                  <div className={s.bcTop}>
                    <svg width="44" height="44" viewBox="0 0 44 44"><rect width="44" height="44" rx="11" fill="#12161D" /><path d={identicon(b.name, 28)} fill="#3a81d7" transform="translate(8 8)" /></svg>
                    <div>
                      <div style={{ fontSize: 16, fontWeight: 500 }}>{b.name}</div>
                      <div className="lbl" style={{ marginTop: 2 }}>{b.note || DIRLBL[b.direction ?? ""]}</div>
                    </div>
                  </div>
                  <div className={s.bcFoot}>
                    <div>
                      <div className="lbl">30 days</div>
                      <div className={`num ${up ? "up" : "down"}`} style={{ fontSize: 22 }}>{pct(ret, true)}</div>
                    </div>
                    <div className={s.bcCta}>
                      <span className="chip">Crypto · {b.visibility === "public" ? "Public strategy" : "Results only"}</span>
                      <button className={`${p.btn} ${p.sm}`} onClick={() => nav("/bot/" + encodeURIComponent(b.name))}>Open</button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className={p.statcell}>
      <div className="lbl">{label}</div>
      <div className={`num ${p.statBig}`}>{value}</div>
    </div>
  );
}
function avgWin(wins: (number | null)[]): string {
  const vals = wins.filter((w): w is number => w != null);
  if (!vals.length) return "–";
  return Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) + "%";
}
