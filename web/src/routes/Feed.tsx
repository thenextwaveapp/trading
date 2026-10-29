import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { botColor } from "../lib/brand";
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
import type { DbBot, DbEvent, DbProfile } from "../db/types";
import { dol, identicon, pct } from "../lib/format";
import { RowsSkeleton } from "../components/Skeleton";
import s from "./Feed.module.css";

function rel(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "now";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

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
  const [liked, setLiked] = useState<Set<string>>(new Set());
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

  const toggleLike = (id: string) =>
    setLiked((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

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
          feed.map((e) => (
            <Post
              key={e.id}
              e={e}
              bot={e.bot_name ? botMap.get(e.bot_name) : undefined}
              variant={e.bot_name ? liveByName.get(e.bot_name) : undefined}
              liked={liked.has(e.id)}
              onLike={() => toggleLike(e.id)}
              nav={nav}
            />
          ))
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

function Post({ e, bot, variant, liked, onLike, nav }: {
  e: DbEvent; bot?: DbBot; variant?: Variant; liked: boolean; onLike: () => void; nav: (p: string) => void;
}) {
  const pay = e.payload ?? {};
  const color = bot ? botColor(bot) : "#5e8fd8";
  const builderHandle = bot?.builder?.handle ?? e.actor_handle ?? null;
  const name = e.bot_name ?? (e.actor_handle ? "@" + e.actor_handle : "Someone");

  // social (non-trade) events render as a slim row
  if (e.type !== "entered" && e.type !== "exited") {
    const verb =
      e.type === "followed" ? "followed a builder"
        : e.type === "copied" ? `copied ${String(pay.from_bot_name ?? "a bot")}`
          : e.type === "kill_switch" ? "hit its kill switch" : e.type;
    return (
      <div className={`card ${s.post}`}>
        <div className={s.pHead}>
          <Avatar seed={e.actor_handle ? "@" + e.actor_handle : name} color={e.type === "kill_switch" ? "#ff5c6c" : "#3ddc97"} size={38} />
          <div className={s.pWho}>
            <div className={s.pName}>{e.actor_handle ? "@" + e.actor_handle : name} <span className="muted" style={{ fontWeight: 400 }}>{verb}</span></div>
          </div>
          <span className={s.pTime}>{rel(e.ts)}</span>
        </div>
      </div>
    );
  }

  const ticker = String(pay.ticker ?? "");
  const entered = e.type === "entered";
  const side = (pay.side as string) ?? bot?.direction ?? null;
  const openPos = variant?.open?.find((o) => o.ticker === ticker);
  const unreal = openPos?.upct != null ? openPos.upct * 100 : null;
  const net = typeof pay.net === "number" ? pay.net * 100 : null;
  const shownPct = entered ? unreal : net;
  const up = (shownPct ?? 0) >= 0;

  return (
    <div className={`card ${s.post}`}>
      <div className={s.pHead}>
        <Avatar seed={name} color={color} size={38} />
        <div className={s.pWho}>
          <div className={s.pName}>
            <span className="lk" onClick={() => nav("/bot/" + encodeURIComponent(name))}>{name}</span>
          </div>
          {builderHandle && (
            <div className={s.pSub}>
              <span className="lk" onClick={() => nav("/builder/" + encodeURIComponent(builderHandle))}>@{builderHandle}</span>
            </div>
          )}
        </div>
        <span className={s.pTime}>{rel(e.ts)}</span>
      </div>

      <div className={s.trade}>
        <div className={s.tradeTop}>
          <div>
            <div className={s.tkrRow}>
              <span className={s.tkr}>{ticker}</span>
              {side && <span className={`${s.sideChip} ${side === "short" ? s.sideShort : s.sideLong}`}>{side.toUpperCase()}</span>}
            </div>
            {entered && pay.entry != null && <div className={s.price}>Entry ${Number(pay.entry).toLocaleString(undefined, { maximumFractionDigits: 8 })}</div>}
          </div>
          <div>
            <div className={`num ${s.pnl} ${shownPct == null ? "muted" : up ? "up" : "down"}`}>
              {shownPct == null ? "—" : pct(shownPct, true)}
            </div>
            <div className={s.pnlLbl}>{entered ? "Unrealized" : "Realized"}</div>
          </div>
        </div>

        <button className={`copyBtn block ${s.mimic}`} onClick={() => nav("/bot/" + encodeURIComponent(name))}>
          Copy
        </button>

        <div className={s.tradeFoot}>
          <span className={s.statusDot}>
            <span className={entered ? "liveDot" : ""} style={!entered ? { width: 6, height: 6, borderRadius: "50%", background: "var(--muted)", display: "inline-block" } : undefined} />
            {entered ? "New trade" : "Closed"}
          </span>
          <span>{entered ? "Opened" : "Closed"} {new Date(e.ts).toLocaleDateString()}</span>
        </div>
      </div>

      <div className={s.actions}>
        <button className={s.action} aria-label="Comment">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M2 3.5h12v8H6l-3 2.5v-2.5H2z" /></svg>
        </button>
        <button className={s.action} aria-label="Repost">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M3 5.5 5 3.5 7 5.5M5 3.5v6a1 1 0 0 0 1 1h5M13 10.5l-2 2-2-2M11 12.5v-6a1 1 0 0 0-1-1H5" /></svg>
        </button>
        <button className={`${s.action} ${liked ? s.liked : ""}`} aria-label="Like" onClick={onLike}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill={liked ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.4"><path d="M8 13.5S2 10 2 5.8A2.8 2.8 0 0 1 8 4a2.8 2.8 0 0 1 6 1.8C14 10 8 13.5 8 13.5Z" /></svg>
        </button>
        <button className={s.action} aria-label="Share" style={{ marginLeft: "auto" }}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M14 2 7 9M14 2l-4.5 12-2.5-5-5-2.5L14 2Z" /></svg>
        </button>
      </div>
    </div>
  );
}
