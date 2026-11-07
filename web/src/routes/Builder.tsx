import { botColor } from "../lib/brand";
import { Settings } from "lucide-react";
import { useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { useAuth, useCurrentHandle } from "../auth";
import { useData } from "../api/context";
import { copyBotToDraft, useBots, useEvents, useProfile } from "../db/queries";
import type { DbBot } from "../db/types";
import { BackBar } from "../components/cells";
import { BotAvatar, UserAvatar } from "../components/Avatar";
import FeedRow from "../components/FeedRow";
import { DIRLBL, MKTLBL, pct, windowReturn } from "../lib/format";
import { edgeGlow } from "../lib/fx";
import p from "./pages.module.css";
import s from "./Builder.module.css";
import r from "./build/build.module.css";
import NotFound from "./NotFound";
import { botPath } from "../lib/paths";

export default function Builder() {
  const nav = useNavigate();
  const loc = useLocation();
  // A :handle in the URL shows that builder; otherwise the signed-in user.
  // Canonical form is /@handle; the catch-all route sends non-@ paths to 404.
  const { handle: rawParam } = useParams();
  const isLegacyRoute = loc.pathname.startsWith("/builder");
  const param = rawParam?.startsWith("@") ? rawParam.slice(1) : rawParam;
  const { user, profile: myProfile } = useAuth();
  const me = useCurrentHandle();
  const handle = param ?? me ?? null;
  const badPath = !!rawParam && !rawParam.startsWith("@") && !isLegacyRoute;
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
  const byName = useMemo(() => new Map(live.bots.map((v) => [v.name, v])), [live.bots]);

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

  // The catch-all /:handle route only serves @-prefixed paths; anything else
  // is a genuinely unknown URL.
  if (badPath) return <NotFound />;

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
          <UserAvatar
            handle={handle}
            name={profile?.display_name}
            url={profile?.avatar_url}
            color={profile?.avatar_color || undefined}
            size={112}
          />
          {/* flex-none keeps the hero avatar from squeezing when the name wraps */}
          <div className={s.heroMain}>
            <h1 className={s.h1}>@{handle}</h1>
            {profile?.bio && <div className={s.quote}>{profile.bio}</div>}
            <div className={s.chips}>
              <span className="chip">{liveBots.length} bots live</span>
              <span className="chip">{totalTrades} trades</span>
              {isMe && (
                <button
                  className={s.settingsBtn}
                  onClick={() => nav("/settings")}
                  aria-label="Settings"
                  title="Settings"
                >
                  <Settings size={16} strokeWidth={1.6} />
                </button>
              )}
            </div>
          </div>
        </section>

        <section className={s.stats}>
          <Stat label="Bots live now" value={String(liveBots.length)} />
          <Stat label="Public & shared" value={String(bots.length)} />
          <Stat label="Total trades" value={totalTrades.toLocaleString()} />
          <Stat label="Avg win rate" value={avgWin(bots.map((x) => x.v?.win ?? null))} />
        </section>

        {bots.length === 0 ? (
          <div className="muted" style={{ padding: "8px 0" }}>No public bots.</div>
        ) : (
          <div className={`${s.grid} ${r.mono}`}>
            {bots.map(({ b, ret }) => {
              const up = ret >= 0;
              return (
                <div
                  key={b.id}
                  className={s.bc}
                  style={{ "--bot": botColor(b) } as React.CSSProperties}
                  onMouseMove={edgeGlow}
                  onClick={() => nav(botPath(b))}
                >
                  <div className={s.bcTop}>
                    <BotAvatar seed={b.name} color={botColor(b)} size={34} />
                    <div style={{ minWidth: 0 }}>
                      <div className={r.kName}>{b.name}</div>
                      <div className="lbl" style={{ marginTop: 2 }}>
                        {MKTLBL[b.market] ?? b.market} · {b.note || DIRLBL[b.direction ?? ""]}
                      </div>
                    </div>
                  </div>
                  <div className={s.bcFoot}>
                    <div>
                      <div className="lbl">30 days</div>
                      <div className={`num ${up ? "up" : "down"}`} style={{ fontSize: 22 }}>{pct(ret, true)}</div>
                    </div>
                    <div className={s.bcCta}>
                      <span className="chip">{b.visibility === "public" ? "Public strategy" : "Results only"}</span>
                      {(b.visibility === "public" || (user && b.owner === user.id)) && (
                        <button
                          className="copyBtn"
                          disabled={copyingId === b.id}
                          onClick={(e) => { e.stopPropagation(); void handleCopy(b); }}
                        >
                          {copyingId === b.id ? "…" : "Copy"}
                        </button>
                      )}
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
              <FeedRow key={e.id} e={e} bot={e.bot_name ? botByName.get(e.bot_name) : undefined} live={e.bot_name ? byName.get(e.bot_name) : undefined} onOpen={nav} />
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
    <div className={s.statcell}>
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
