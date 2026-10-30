import { botColor } from "../lib/brand";
import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAuth, useCurrentHandle } from "../auth";
import { useData } from "../api/context";
import { copyBotToDraft, useBots, useEvents, useProfile } from "../db/queries";
import type { DbBot } from "../db/types";
import { BackBar } from "../components/cells";
import FeedRow from "../components/FeedRow";
import { DIRLBL, identicon, pct, windowReturn } from "../lib/format";
import p from "./pages.module.css";
import s from "./Builder.module.css";

export default function Builder() {
  const nav = useNavigate();
  // A :handle in the URL shows that builder; otherwise the signed-in user.
  const { handle: param } = useParams();
  const { user, profile: myProfile } = useAuth();
  const me = useCurrentHandle();
  const handle = param ?? me ?? null;
  const isMe = !!me && handle === me;
  const live = useData();
  const { data: profile } = useProfile(handle ?? "");
  const { data: allBots } = useBots();
  const [copyingId, setCopyingId] = useState<string | null>(null);

  const handleCopy = async (bot: DbBot) => {
    if (!user) {
      nav("/signin");
      return;
    }
    setCopyingId(bot.id);
    const { data } = await copyBotToDraft(
      bot,
      user.id,
      myProfile?.default_bot_visibility ?? "private",
    );
    setCopyingId(null);
    if (data?.id) {
      nav(`/build/compose?bot=${encodeURIComponent(data.id)}`);
    }
  };

  const mine = useMemo(() => (allBots ?? []).filter((b) => b.builder?.handle === handle), [allBots, handle]);
  const byName = useMemo(() => new Map(live.variants.map((v) => [v.name, v])), [live.variants]);

  const bots = mine.map((b) => {
    const v = byName.get(b.name);
    const ret = v ? (v.curve.length ? windowReturn(v.curve, 30, live.now) : v.ret) : (b.bt ?? 0);
    return { b, v, ret };
  });

  const liveBots = bots.filter((x) => x.b.stage === "deployed");
  const totalTrades = bots.reduce((a, x) => a + (x.v?.closed ?? 0), 0);

  const { data: events } = useEvents(60);
  const [showAllActivity, setShowAllActivity] = useState(false);
  const mineNames = useMemo(() => new Set(mine.map((b) => b.name)), [mine]);
  const botByName = useMemo(() => new Map(mine.map((b) => [b.name, b] as const)), [mine]);
  const activity = useMemo(
    () => (events ?? []).filter((e) => (e.bot_name ? mineNames.has(e.bot_name) : e.actor_handle === handle)).slice(0, 40),
    [events, mineNames, handle],
  );

  // Logged out with no :handle — nobody to show.
  if (!handle) {
    return (
      <div className={p.body} style={{ padding: 24 }}>
        <div className="muted">Log in to see your builder profile.</div>
        <button className={`${p.btn} ${p.sm}`} style={{ marginTop: 12 }} onClick={() => nav("/signin")}>
          Sign in
        </button>
      </div>
    );
  }

  if (profile && profile.profile_public === false && !isMe) {
    return (
      <>
        <BackBar fallbackPath="/leaderboard" fallbackLabel="Leaderboard" />
        <div className={p.body} style={{ paddingTop: 40 }}>
          <div className="muted">@{handle}'s builder profile is private.</div>
        </div>
      </>
    );
  }

  return (
    <>
      <BackBar fallbackPath="/leaderboard" fallbackLabel="Leaderboard" />

      <div className={`${p.narrow} ${p.body}`}>
        <section className={s.hero}>
          {profile?.avatar_url ? (
            <img src={profile.avatar_url} alt="" width={112} height={112}
                 style={{ flex: "none", borderRadius: "50%", objectFit: "cover", background: "#12161D" }} />
          ) : (
            <svg width="112" height="112" viewBox="0 0 112 112">
              <rect width="112" height="112" rx="56" fill="#12161D" />
              <path d={identicon("@" + handle, 64)} fill={profile?.avatar_color || "#3a81d7"} transform="translate(24 24)" />
            </svg>
          )}
          <div className={s.heroMain}>
            <h1 className={s.h1}>@{handle}</h1>
            {profile?.bio && <div className={s.quote}>{profile.bio}</div>}
            <div className={s.chips}>
              <span className="chip">{liveBots.length} bots live</span>
              <span className="chip">{totalTrades} trades</span>
              {isMe && (
                <button className={`${p.btn} ${p.sm}`} onClick={() => nav("/settings")}>
                  Privacy &amp; sharing
                </button>
              )}
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
                    <svg width="44" height="44" viewBox="0 0 44 44"><rect width="44" height="44" rx="22" fill="#12161D" /><path d={identicon(b.name, 28)} fill={botColor(b)} transform="translate(8 8)" /></svg>
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
                      <div style={{ display: "flex", gap: 6 }}>
                        {(b.visibility === "public" || (user && b.owner === user.id)) && (
                          <button
                            className={`${p.btn} ${p.sm}`}
                            disabled={copyingId === b.id}
                            onClick={() => void handleCopy(b)}
                          >
                            {copyingId === b.id ? "…" : "Copy"}
                          </button>
                        )}
                        <button className={`${p.btn} ${p.sm}`} onClick={() => nav("/bot/" + encodeURIComponent(b.name))}>Open</button>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className={p.sectionHead}><h2 className={p.h2}>Activity</h2></div>
        {activity.length === 0 ? (
          <div className="muted" style={{ padding: "8px 0" }}>No activity yet.</div>
        ) : (
          <div className={s.feed}>
            {(showAllActivity ? activity : activity.slice(0, 3)).map((e) => (
              <FeedRow key={e.id} e={e} bot={e.bot_name ? botByName.get(e.bot_name) : undefined} variant={e.bot_name ? byName.get(e.bot_name) : undefined} onOpen={nav} />
            ))}
            {activity.length > 3 && (
              <button className={s.more} onClick={() => setShowAllActivity((x) => !x)}>
                {showAllActivity ? "Show less" : `Show ${activity.length - 3} more`}
              </button>
            )}
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
