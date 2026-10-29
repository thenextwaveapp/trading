import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAssistant } from "../assistant/AssistantProvider";
import { useAuth, useCurrentHandle } from "../auth";
import { useData } from "../api/context";
import type { Variant } from "../api/types";
import {
  followBuilder,
  unfollowBuilder,
  useBots,
  useEvents,
  useMyFollows,
  usePublicProfiles,
} from "../db/queries";
import type { DbBot, DbProfile } from "../db/types";
import { dol, identicon, pct } from "../lib/format";
import { RowsSkeleton } from "../components/Skeleton";
import FeedRow from "../components/FeedRow";
import s from "./Feed.module.css";

function Avatar({ seed, color, url, size = 38 }: { seed: string; color: string; url?: string | null; size?: number }) {
  if (url) return <img src={url} alt="" width={size} height={size} style={{ borderRadius: "50%", objectFit: "cover", background: "#12161D", flex: "none" }} />;
  const inner = Math.round(size * 0.62);
  const off = Math.round((size - inner) / 2);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flex: "none" }}>
      <rect width={size} height={size} rx={size / 2} fill="#12161D" />
      <path d={identicon(seed, inner)} fill={color} transform={`translate(${off} ${off})`} />
    </svg>
  );
}

const TABS = [
  ["moves", "Moves"],
  ["trending", "Trending"],
  ["following", "Following"],
  ["recent", "Recent"],
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
    const m = new Map<string, Variant>();
    for (const v of live.variants) m.set(v.name, v);
    return m;
  }, [live]);

  const topBots = useMemo(
    () => live.variants.slice().sort((a, b) => b.ret - a.ret).filter((v) => v.closed > 0 || v.open.length > 0).slice(0, 5),
    [live],
  );
  const topBotNames = useMemo(() => new Set(topBots.map((v) => v.name)), [topBots]);

  const feed = useMemo(() => {
    let xs = (events ?? []).slice();
    if (tab === "moves") {
      xs = xs.filter((e) => e.type === "exited")
        .sort((a, b) => Math.abs(Number(b.payload?.net ?? 0)) - Math.abs(Number(a.payload?.net ?? 0)));
    } else if (tab === "trending") {
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

  return (
    <div className={s.wrap}>
      <div>
        <div className={s.tabs}>
          {TABS.map(([k, label]) => (
            <button key={k} className={`${s.tab} ${tab === k ? s.on : ""}`} onClick={() => setTab(k)}>{label}</button>
          ))}
        </div>

        {loading ? (
          <RowsSkeleton rows={6} avatar />
        ) : feed.length === 0 ? (
          <div className="muted" style={{ padding: "40px 0" }}>
            {tab === "following" ? "Follow some builders to see their trades here." : "Nothing here yet."}
          </div>
        ) : (
          <div className={s.list}>
            {feed.map((e) => (
              <FeedRow
                key={e.id}
                e={e}
                bot={e.bot_name ? botMap.get(e.bot_name) : undefined}
                variant={e.bot_name ? liveByName.get(e.bot_name) : undefined}
                onOpen={nav}
              />
            ))}
          </div>
        )}
      </div>

      <aside className={s.rail}>
        {user && (
          <div className={`card ${s.meCard}`} style={{ cursor: "pointer" }} onClick={() => nav(handle ? "/builder/" + handle : "/settings")}>
            <Avatar seed={"@" + (handle ?? "me")} color={profile?.avatar_color || "#3a81d7"} url={profile?.avatar_url} size={42} />
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
              <div key={v.name} className={s.railRow} onClick={() => nav("/bot/" + encodeURIComponent(v.name))}>
                <Avatar seed={v.name} color={v.color || "#3a81d7"} size={30} />
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
                  <span onClick={() => nav("/builder/" + encodeURIComponent(pr.handle))} style={{ display: "inline-flex" }}>
                    <Avatar seed={"@" + pr.handle} color={pr.avatar_color || "#3a81d7"} url={pr.avatar_url} size={30} />
                  </span>
                  <div style={{ minWidth: 0 }} onClick={() => nav("/builder/" + encodeURIComponent(pr.handle))}>
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
  );
}
