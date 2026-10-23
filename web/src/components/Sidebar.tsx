import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useData } from "../api/context";
import { useAuth, useCurrentHandle } from "../auth";
import { ago, pct, START } from "../lib/format";
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
  settings: (
    <svg className={s.niIc} width="17" height="17" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="2.2" stroke="currentColor" strokeWidth="1.3" />
      <path d="M8 1.2v2M8 12.8v2M1.2 8h2M12.8 8h2M3.2 3.2l1.4 1.4M11.4 11.4l1.4 1.4M12.8 3.2l-1.4 1.4M4.6 11.4 3.2 12.8" stroke="currentColor" strokeWidth="1.15" />
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
  const d = useData();
  const nav = useNavigate();
  const loc = useLocation();
  const { user } = useAuth();
  const myHandle = useCurrentHandle();
  const N = d.variants.length;
  const fleetRet = (d.hero.fleet_pnl / (N * START)) * 100;
  const liveOk = d.running && !d.paused;

  // Replay the plane fly animation each time the sidebar opens.
  const [flyKey, setFlyKey] = useState(0);
  const wasCollapsed = useRef(collapsed);
  useEffect(() => {
    if (wasCollapsed.current && !collapsed) setFlyKey((k) => k + 1);
    wasCollapsed.current = collapsed;
  }, [collapsed]);

  const onFleet = loc.pathname.startsWith("/fleet") || loc.pathname.startsWith("/bot");
  const statusTxt = liveOk ? "Fleet is live" : d.paused ? "Fleet paused" : "Fleet is down";
  const home = { label: "Home", path: "/", icon: "fleet" as const, active: loc.pathname === "/" };
  const board = { label: "Leaderboard", path: "/leaderboard", icon: "leaderboard" as const, active: loc.pathname.startsWith("/leaderboard") };
  const navItems: { label: string; path: string; icon: keyof typeof icons; active: boolean }[] = user
    ? [
        home,
        { label: "Build", path: "/build", icon: "build", active: loc.pathname.startsWith("/build") },
        board,
        { label: "Settings", path: "/settings", icon: "settings", active: loc.pathname.startsWith("/settings") },
      ]
    : [home, board];

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

      <div>
        <div className={s.cap}>YOUR FLEETS</div>
        <button className={`${s.fl} ${onFleet ? s.on : ""}`} onClick={() => nav("/fleet")} title="Paper Fleet">
          <span className={s.sq} />
          <span className={`${s.flBody} ${s.txt}`}>
            <span className={s.flName}>Paper Fleet</span>
            <span className={`num ${s.flSub}`}>{N} bots</span>
          </span>
          <span className={`num ${s.txt} ${fleetRet >= 0 ? s.up : s.dn}`} style={{ fontSize: 12 }}>
            {pct(fleetRet, true)}
          </span>
        </button>
      </div>

      <nav className={s.nav}>
        <div className={s.cap}>PAPER FLEET</div>
        {navItems.map((it) => (
          <button
            key={it.path}
            className={`${s.ni} ${it.active ? s.on : ""}`}
            onClick={() => nav(it.path)}
            title={it.label}
          >
            {icons[it.icon]}
            <span className={s.txt}>{it.label}</span>
          </button>
        ))}
        {!user && (
          <button
            className={s.ni}
            onClick={() => nav("/signin")}
            title="Start free"
            style={{ background: "var(--accent, #5e8fd8)", color: "#fff", justifyContent: "center", marginTop: 8 }}
          >
            <span className={s.txt}>Start free</span>
          </button>
        )}
      </nav>

      <div className={s.spacer} />

      <div className={s.status} title={`${statusTxt} · updated ${ago(d.state_age_s)}`}>
        <div className={s.statusRow}>
          <span className={liveOk ? s.live : s.down} />
          <span className={s.txt}>{statusTxt}</span>
        </div>
        <div className={`${s.updated} ${s.txt}`}>Updated {ago(d.state_age_s)}</div>
      </div>

      <button
        className={`${s.ni} ${loc.pathname === "/signin" ? s.on : ""}`}
        onClick={() => nav(user ? "/settings" : "/signin")}
        title={user ? `@${myHandle ?? "account"}` : "Sign in"}
      >
        <svg className={s.niIc} width="17" height="17" viewBox="0 0 16 16" fill="none">
          <circle cx="8" cy="5" r="2.6" stroke="currentColor" strokeWidth="1.3" />
          <path d="M2.5 14c0-3 2.5-4.6 5.5-4.6S13.5 11 13.5 14" stroke="currentColor" strokeWidth="1.3" />
        </svg>
        <span className={s.txt}>{user ? `@${myHandle ?? "you"}` : "Sign in"}</span>
      </button>
    </aside>
  );
}
