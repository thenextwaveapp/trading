import { botColor } from "../lib/brand";
import { Fragment, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth, useCurrentHandle } from "../auth";
import { useBuildBots } from "../db/queries";
import { resumePath, STAGES } from "../routes/build/stages";
import s from "./Sidebar.module.css";

const icons = {
  fleet: (
    <svg className={s.niIc} width="17" height="17" viewBox="0 0 16 16" fill="none">
      <rect x="1.5" y="1.5" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3" />
      <rect x="9.5" y="1.5" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3" />
      <rect x="1.5" y="9.5" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3" />
      <rect x="9.5" y="9.5" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  ),
  build: (
    <svg className={s.niIc} width="17" height="17" viewBox="0 0 16 16" fill="none">
      <path d="M6 1.8v4L2.6 11.4A1.6 1.6 0 0 0 4 13.9h8a1.6 1.6 0 0 0 1.4-2.5L10 5.8v-4" stroke="currentColor" strokeWidth="1.3" />
      <path d="M5 1.8h6M4.6 9h6.8" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  ),
  leaderboard: (
    <svg className={s.niIc} width="17" height="17" viewBox="0 0 16 16" fill="none">
      <path d="M2 14h12" stroke="currentColor" strokeWidth="1.3" />
      <rect x="2.8" y="7" width="2.6" height="5" rx=".5" fill="currentColor" />
      <rect x="6.7" y="3.5" width="2.6" height="8.5" rx=".5" fill="currentColor" />
      <rect x="10.6" y="9" width="2.6" height="3" rx=".5" fill="currentColor" />
    </svg>
  ),
  market: (
    <svg className={s.niIc} width="17" height="17" viewBox="0 0 16 16" fill="none">
      <path d="M4 2.5v2M4 10.5v3M12 1.5v3M12 11v1.5" stroke="currentColor" strokeWidth="1.2" />
      <rect x="2.5" y="4.5" width="3" height="6" rx=".6" stroke="currentColor" strokeWidth="1.2" />
      <rect x="10.5" y="4.5" width="3" height="6.5" rx=".6" fill="currentColor" />
    </svg>
  ),
  trophy: (
    <svg className={s.niIc} width="17" height="17" viewBox="0 0 16 16" fill="none">
      <path d="M4.5 2h7v3.2a3.5 3.5 0 0 1-7 0V2Z" stroke="currentColor" strokeWidth="1.3" />
      <path d="M4.5 3H2.6a2 2 0 0 0 2.2 2.6M11.5 3h1.9a2 2 0 0 1-2.2 2.6" stroke="currentColor" strokeWidth="1.2" />
      <path d="M8 8.6V11M5.5 14h5M6.6 11h2.8v3" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  ),
  settings: (
    <svg className={s.niIc} width="17" height="17" viewBox="0 0 16 16" fill="none">
      <path d="M2.5 4.5h4M9.5 4.5h4M2.5 8h7M12 8h1.5M2.5 11.5h2M7.5 11.5h6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
      <circle cx="8" cy="4.5" r="1.4" fill="currentColor" />
      <circle cx="11" cy="8" r="1.4" fill="currentColor" />
      <circle cx="6" cy="11.5" r="1.4" fill="currentColor" />
    </svg>
  ),
};

export default function Sidebar({
  collapsed,
  onToggle,
  mobileOpen = false,
}: {
  collapsed: boolean;
  onToggle: () => void;
  mobileOpen?: boolean;
}) {
  const nav = useNavigate();
  const loc = useLocation();
  const { user } = useAuth();
  const myHandle = useCurrentHandle();
  const [buildNonce, setBuildNonce] = useState(0);
  const { data: buildBots } = useBuildBots(user?.id ?? null, buildNonce);
  const activeBotId = new URLSearchParams(loc.search).get("bot");
  const stageLabel = new Map(STAGES.map((x) => [x.key, x.label]));
  useEffect(() => {
    setBuildNonce((n) => n + 1);
  }, [loc.pathname, loc.search]);
  useEffect(() => {
    if (!user) return;
    const t = setInterval(() => setBuildNonce((n) => n + 1), 10_000);
    return () => clearInterval(t);
  }, [user]);
  // Replay the plane fly animation each time the sidebar opens.
  const [flyKey, setFlyKey] = useState(0);
  const wasCollapsed = useRef(collapsed);
  useEffect(() => {
    if (wasCollapsed.current && !collapsed) setFlyKey((k) => k + 1);
    wasCollapsed.current = collapsed;
  }, [collapsed]);

  const home = {
    label: "Home",
    path: user ? "/fleet" : "/",
    icon: "fleet" as const,
    active: user ? loc.pathname.startsWith("/fleet") : loc.pathname === "/",
  };
  const market = { label: "Market", path: "/market", icon: "market" as const, active: loc.pathname.startsWith("/market") };
  const board = { label: "Leaderboard", path: "/leaderboard", icon: "leaderboard" as const, active: loc.pathname.startsWith("/leaderboard") };
  const challenges = { label: "Challenges", path: "/challenges", icon: "trophy" as const, active: loc.pathname.startsWith("/challenge") };
  const navItems: { label: string; path: string; icon: keyof typeof icons; active: boolean }[] = user
    ? [
        home,
        market,
        { label: "Build", path: "/build", icon: "build", active: loc.pathname.startsWith("/build") },
        board,
        challenges,
        { label: "Settings", path: "/settings", icon: "settings", active: loc.pathname.startsWith("/settings") },
      ]
    : [home, market, board, challenges];

  return (
    <aside className={`${s.side} ${collapsed ? s.collapsed : ""} ${mobileOpen ? s.open : ""}`}>
      <div className={s.head}>
        <button className={s.wm} onClick={onToggle} title={collapsed ? "Open sidebar" : "Collapse sidebar"} aria-label="Toggle sidebar">
          <svg key={flyKey} className={`${s.plane} ${s.planeFly}`} width="23" height="23" viewBox="0 0 200 200" fill="none" aria-hidden>
            <path d="M170 30 L30 95 L95 125 L170 30 Z" fill="#E9ECF1" />
            <path d="M170 30 L107 131 L122 170 L137 137 L170 30 Z" fill="#5E8FD8" />
          </svg>
          <span className={s.txt}>paper fleet</span>
        </button>
      </div>

      <nav className={s.nav}>
        {navItems.map((it) => (
          <Fragment key={it.path}>
            <button
              className={`${s.ni} ${it.active ? s.on : ""}`}
              onClick={() => nav(it.path)}
              title={it.label}
            >
              {icons[it.icon]}
              <span className={s.txt}>{it.label}</span>
            </button>
            {it.label === "Build" && !!buildBots?.length && (
              <div className={s.buildList}>
                {buildBots.map((b) => (
                  <button
                    key={b.id}
                    className={`${s.buildItem} ${activeBotId === b.id ? s.buildOn : ""}`}
                    onClick={() => nav(resumePath(b.stage, b.id, b.name))}
                    title={`${b.name} — ${stageLabel.get(b.stage) ?? b.stage}`}
                  >
                    <span
                      className={s.buildDot}
                      style={{ background: botColor(b) }}
                    />
                    <span className={s.buildName}>{b.name}</span>
                    <span className={s.buildStage}>
                      {stageLabel.get(b.stage) ?? b.stage}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </Fragment>
        ))}
        {!user && (
          <button
            className={s.ni}
            onClick={() => nav("/?auth=signup")}
            title="Start free"
            style={{ background: "var(--accent, #5e8fd8)", color: "#fff", justifyContent: "center", marginTop: 8 }}
          >
            <span className={s.txt}>Start free</span>
          </button>
        )}
      </nav>

      <div className={s.spacer} />

      <button
        className={s.ni}
        onClick={() => nav(user ? "/settings" : "/?auth=signin")}
        title={user ? `@${myHandle ?? "account"}` : "Log in"}
      >
        <svg className={s.niIc} width="17" height="17" viewBox="0 0 16 16" fill="none">
          <circle cx="8" cy="5" r="2.6" stroke="currentColor" strokeWidth="1.3" />
          <path d="M2.5 14c0-3 2.5-4.6 5.5-4.6S13.5 11 13.5 14" stroke="currentColor" strokeWidth="1.3" />
        </svg>
        <span className={s.txt}>{user ? `@${myHandle ?? "you"}` : "Log in"}</span>
      </button>
    </aside>
  );
}
