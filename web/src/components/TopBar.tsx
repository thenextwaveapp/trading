import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth, useCurrentHandle } from "../auth";
import { identicon } from "../lib/format";
import SearchPalette from "./SearchPalette";
import s from "./TopBar.module.css";

const gearIcon = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
);

const searchIcon = (
  <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor">
    <circle cx="7" cy="7" r="5" strokeWidth="1.4" />
    <path d="M11 11l3.5 3.5" strokeWidth="1.4" strokeLinecap="round" />
  </svg>
);

export default function TopBar() {
  const nav = useNavigate();
  const loc = useLocation();
  const { user, profile } = useAuth();
  const handle = useCurrentHandle();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState(false);

  useEffect(() => setOpen(false), [loc.pathname]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearch(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const items = user
    ? [
        { l: "Home", p: "/feed" },
        { l: "Market", p: "/market" },
        { l: "Fleet", p: "/fleet" },
        { l: "Build", p: "/build" },
        { l: "Leaderboard", p: "/leaderboard" },
        { l: "Challenges", p: "/challenges" },
      ]
    : [
        { l: "Home", p: "/" },
        { l: "Market", p: "/market" },
        { l: "Leaderboard", p: "/leaderboard" },
        { l: "Challenges", p: "/challenges" },
      ];

  const isActive = (p: string) =>
    p === "/" ? loc.pathname === "/"
      : loc.pathname.startsWith(p) ||
        (p === "/challenges" && loc.pathname.startsWith("/challenge"));

  const go = (p: string) => () => nav(p);

  const links = items.map((it) => (
    <button key={it.p} className={`${s.link} ${isActive(it.p) ? s.active : ""}`} onClick={go(it.p)}>
      {it.l}
    </button>
  ));

  return (
    <header className={s.bar}>
      <button className={s.menuBtn} aria-label="Menu" onClick={() => setOpen((o) => !o)}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
          <path d="M3 6h18M3 12h18M3 18h18" />
        </svg>
      </button>

      <span className={s.brand} onClick={go(user ? "/feed" : "/")}>
        <svg width="20" height="20" viewBox="0 0 200 200" fill="none" aria-hidden>
          <path d="M170 30 L30 95 L95 125 L170 30 Z" fill="#E9ECF1" />
          <path d="M170 30 L107 131 L122 170 L137 137 L170 30 Z" fill="#5E8FD8" />
        </svg>
        paper fleet
      </span>

      <nav className={s.nav}>{links}</nav>

      <div className={s.right}>
        <button className={s.search} onClick={() => setSearch(true)} aria-label="Search">
          {searchIcon}
          <span className={s.searchText}>Search</span>
          <span className={s.kbd}>⌘K</span>
        </button>
        {user ? (
          <>
            <button className={s.gear} aria-label="Settings" title="Settings" onClick={go("/settings")}>
              {gearIcon}
            </button>
            <span
              className={s.avatar}
              title={handle ? `@${handle}` : "Your profile"}
              onClick={() => nav(handle ? "/builder/" + encodeURIComponent(handle) : "/settings")}
            >
              {profile?.avatar_url ? (
                <img src={profile.avatar_url} alt="" width={32} height={32}
                     style={{ borderRadius: "50%", objectFit: "cover", background: "#12161D" }} />
              ) : (
                <svg width="32" height="32" viewBox="0 0 32 32">
                  <rect width="32" height="32" rx="16" fill="#12161D" />
                  <path d={identicon("@" + (handle ?? "me"), 20)} fill={profile?.avatar_color || "#3a81d7"} transform="translate(6 6)" />
                </svg>
              )}
            </span>
          </>
        ) : (
          <button className={s.link} onClick={go("/signin")}>Log in</button>
        )}
      </div>

      {open && <div className={s.sheet}>{links}</div>}
      {search && <SearchPalette onClose={() => setSearch(false)} />}
    </header>
  );
}
