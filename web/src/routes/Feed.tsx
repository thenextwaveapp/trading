import { useEffect, useMemo, useState } from "react";
import { ChevronRight, Clock, Crown, Swords, UserCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useMediaQuery } from "../lib/responsive";
import { useAssistant } from "../assistant/AssistantProvider";
import { useAuth, useCurrentHandle } from "../auth";
import { useData } from "../api/context";
import type { Bot } from "../api/types";
import {
  followBuilder,
  unfollowBuilder,
  useBots,
  useEvents,
  useMyFollows,
  usePublicProfiles,
} from "../db/queries";
import type { DbBot, DbProfile } from "../db/types";
import { dol, pct } from "../lib/format";
import { BotAvatar, UserAvatar } from "../components/Avatar";
import { RowsSkeleton } from "../components/Skeleton";
import FeedRow from "../components/FeedRow";
import Segmented from "../components/Segmented";
import p from "./pages.module.css";
import s from "./Feed.module.css";
import { botPath, builderPath } from "../lib/paths";

/* lucide has no trending-up-inside-circle glyph, so compose one in its style:
   same 24px grid, currentColor stroke, round caps */
function TrendCircle({ size = 18 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="12" cy="12" r="10" />
      <polyline points="7 14.5 10.25 11.25 12.75 13.75 17 9.5" />
      <polyline points="14 9.5 17 9.5 17 12.5" />
    </svg>
  );
}

const TABS = [
  ["trending", "Trending", <TrendCircle />],
  ["recent", "Recent", <Clock size={18} strokeWidth={1.5} />],
  ["following", "Following", <UserCheck size={18} strokeWidth={1.5} />],
] as const;
type Tab = (typeof TABS)[number][0];

export default function Feed() {
  const nav = useNavigate();
  const { user, profile } = useAuth();
  const handle = useCurrentHandle();
  const live = useData();
  const { data: events, loading } = useEvents(80);
  const { data: bots } = useBots();
  const { data: profiles } = usePublicProfiles();
  const { data: myFollows } = useMyFollows(user?.id ?? null);

  const [tab, setTab] = useState<Tab>("recent");
  const [follows, setFollows] = useState<Set<string> | null>(null);

  const followed = follows ?? new Set((myFollows ?? []).map((f) => f.builder));

  const botMap = useMemo(() => {
    const m = new Map<string, DbBot>();
    for (const b of bots ?? []) m.set(b.name, b);
    return m;
  }, [bots]);
  const liveByName = useMemo(() => {
    const m = new Map<string, Bot>();
    for (const v of live.bots) m.set(v.name, v);
    return m;
  }, [live]);

  const topBots = useMemo(
    () => live.bots.slice().sort((a, b) => b.ret - a.ret).filter((v) => v.closed > 0 || v.open.length > 0).slice(0, 5),
    [live],
  );
  const topBotNames = useMemo(() => new Set(topBots.map((v) => v.name)), [topBots]);

  const feed = useMemo(() => {
    let xs = (events ?? []).slice();
    if (tab === "trending") {
      xs = xs.filter((e) => e.bot_name && topBotNames.has(e.bot_name));
    } else if (tab === "following") {
      xs = xs.filter((e) => {
        const owner = e.bot_name ? botMap.get(e.bot_name)?.owner : e.actor;
        return owner ? followed.has(owner) : false;
      });
    }
    return xs.slice(0, 50);
  }, [events, tab, topBotNames, botMap, followed]);

  const { setPageContext } = useAssistant();
  useEffect(() => {
    const rows = feed.slice(0, 18).map((e) => {
      const nm = e.bot_name ?? (e.actor_handle ? "@" + e.actor_handle : "Someone");
      const pay = (e.payload ?? {}) as Record<string, unknown>;
      const tk = String(pay.ticker ?? "");
      const net = typeof pay.net === "number" ? ` (${(pay.net * 100).toFixed(1)}%)` : "";
      if (e.type === "entered") return `${nm} opened ${tk}`.trim();
      if (e.type === "exited") return `${nm} exited ${tk}${net}`.trim();
      if (e.type === "copied") return `${nm} copied ${String(pay.from_bot_name ?? "a bot")}`;
      if (e.type === "followed") return `${nm} followed a builder`;
      if (e.type === "kill_switch") return `${nm} tripped its loss limit`;
      return `${nm} ${e.type}`;
    });
    setPageContext({ screen: { title: `Activity feed — ${tab} tab`, rows } });
    return () => setPageContext(null);
  }, [feed, tab, setPageContext]);

  const toggleFollow = async (builderId: string) => {
    if (!user) return nav("/signin");
    const next = new Set(followed);
    const on = next.has(builderId);
    on ? next.delete(builderId) : next.add(builderId);
    setFollows(next);
    on ? await unfollowBuilder(user.id, builderId) : await followBuilder(user.id, builderId);
  };

  const topUsers = (profiles ?? []).filter((p) => p.id !== user?.id).slice(0, 6);

  // On narrow screens the rail collapses (it needs its 312px). Rather than drop
  // its discovery modules to the bottom — unreachable under a long feed — we
  // surface them at the TOP as horizontal carousels, plus quick links to the
  // Leaderboard and Arena (which otherwise only live in the nav/search).
  const showDiscover = useMediaQuery("(max-width: 960px)");

  return (
    <div className={p.shell}>
    <div className={s.wrap}>
      <div>
        {showDiscover && (
          <div className={s.discover}>
            <div className={s.quick}>
              <button className={`${s.quickCard} ${s.qLeaders}`} onClick={() => nav("/leaderboard")}>
                <span className={s.qIcon}><Crown size={18} strokeWidth={1.75} /></span>
                <span className={s.qText}>
                  <span className={s.qTitle}>Leaderboard</span>
                  <span className={s.qSub}>Top performers</span>
                </span>
                <ChevronRight size={16} className={s.qChev} />
              </button>
              <button className={`${s.quickCard} ${s.qArena}`} onClick={() => nav("/challenges")}>
                <span className={s.qIcon}><Swords size={18} strokeWidth={1.75} /></span>
                <span className={s.qText}>
                  <span className={s.qTitle}>Arena</span>
                  <span className={s.qSub}>Live challenges</span>
                </span>
                <ChevronRight size={16} className={s.qChev} />
              </button>
            </div>

            {topBots.length > 0 && (
              <div>
                <div className={s.railTitle}>Trending bots</div>
                <div className={s.hscroll}>
                  {topBots.map((v) => (
                    <button
                      key={v.name}
                      className={s.chip}
                      onClick={() => { const db = botMap.get(v.name); nav(db ? botPath(db) : "/bot/" + encodeURIComponent(v.name)); }}
                    >
                      <BotAvatar seed={v.name} color={v.color || undefined} size={30} />
                      <span className={s.chipName}>{v.name}</span>
                      <span className={`num ${v.ret >= 0 ? "up" : "down"}`} style={{ fontSize: 12 }}>{pct(v.ret, true)}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {topUsers.length > 0 && (
              <div>
                <div className={s.railTitle}>Top builders</div>
                <div className={s.hscroll}>
                  {topUsers.map((pr: DbProfile) => {
                    const on = followed.has(pr.id);
                    return (
                      <div key={pr.id} className={s.bchip}>
                        <span onClick={() => nav(builderPath(pr.handle))} style={{ display: "inline-flex" }}>
                          <UserAvatar handle={pr.handle} name={pr.display_name} url={pr.avatar_url} color={pr.avatar_color || undefined} size={32} />
                        </span>
                        <span className={s.chipName} onClick={() => nav(builderPath(pr.handle))}>@{pr.handle}</span>
                        <button className={`${s.followBtn} ${s.chipFollow} ${on ? s.on : ""}`} onClick={() => void toggleFollow(pr.id)}>
                          {on ? "Following" : "Follow"}
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        <div className={s.tabsRow}>
          <Segmented
            ariaLabel="Feed filter"
            value={tab}
            onChange={setTab}
            block={showDiscover}
            labels={showDiscover ? "always" : "selected"}
            options={TABS.map(([k, label, icon]) => ({ value: k, label, icon }))}
          />
        </div>

        {loading ? (
          <RowsSkeleton rows={6} avatar />
        ) : feed.length === 0 ? (
          <div className={s.empty}>
            <RowsSkeleton rows={6} avatar ghost />
            <div className={`muted ${s.emptyMsg}`}>
              {tab === "following" ? "Follow some builders to see their trades here." : "Nothing here yet."}
            </div>
          </div>
        ) : (
          <div className={s.list}>
            {feed.map((e) => (
              <FeedRow
                key={e.id}
                e={e}
                bot={e.bot_name ? botMap.get(e.bot_name) : undefined}
                live={e.bot_name ? liveByName.get(e.bot_name) : undefined}
                onOpen={nav}
              />
            ))}
          </div>
        )}
      </div>

      <aside className={s.rail}>
        {user && (
          <div className={`card ${s.meCard}`} style={{ cursor: "pointer" }} onClick={() => nav(handle ? builderPath(handle) : "/settings")}>
            <UserAvatar handle={handle} name={profile?.display_name} url={profile?.avatar_url} color={profile?.avatar_color || undefined} size={42} />
            <div style={{ minWidth: 0 }}>
              <div className={s.railName}>{profile?.display_name || (handle ? "@" + handle : "You")}</div>
              {handle && <div className={s.railMeta}>@{handle}</div>}
            </div>
          </div>
        )}

        <div className={`card ${s.railCard}`}>
          <div className={s.railTitle}>Trending bots</div>
          {topBots.length === 0 ? (
            <div className={s.railMeta}>No live bots yet.</div>
          ) : (
            topBots.map((v) => (
              <div key={v.name} className={s.railRow} onClick={() => { const db = botMap.get(v.name); nav(db ? botPath(db) : "/bot/" + encodeURIComponent(v.name)); }}>
                <BotAvatar seed={v.name} color={v.color || undefined} size={30} />
                <div style={{ minWidth: 0 }}>
                  <div className={s.railName}>{v.name}</div>
                  <div className={s.railMeta}>{dol(v.equity)}</div>
                </div>
                <span className={`num ${v.ret >= 0 ? "up" : "down"}`} style={{ marginLeft: "auto", fontSize: 13 }}>{pct(v.ret, true)}</span>
              </div>
            ))
          )}
        </div>

        {topUsers.length > 0 && (
          <div className={`card ${s.railCard}`}>
            <div className={s.railTitle}>Top builders</div>
            {topUsers.map((pr: DbProfile) => {
              const on = followed.has(pr.id);
              return (
                <div key={pr.id} className={s.railRow}>
                  <span onClick={() => nav(builderPath(pr.handle))} style={{ display: "inline-flex" }}>
                    <UserAvatar handle={pr.handle} name={pr.display_name} url={pr.avatar_url} color={pr.avatar_color || undefined} size={30} />
                  </span>
                  <div style={{ minWidth: 0 }} onClick={() => nav(builderPath(pr.handle))}>
                    <div className={s.railName}>@{pr.handle}</div>
                    {pr.display_name && <div className={s.railMeta}>{pr.display_name}</div>}
                  </div>
                  {pr.id !== user?.id && (
                    <button className={`${s.followBtn} ${on ? s.on : ""}`} onClick={() => void toggleFollow(pr.id)}>
                      {on ? "Following" : "Follow"}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </aside>
    </div>
    </div>
  );
}
