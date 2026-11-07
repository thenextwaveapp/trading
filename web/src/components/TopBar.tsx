import { useEffect, useMemo, useState } from "react";
import {
  Crown,
  FlaskConical,
  Globe,
  LogOut,
  Menu,
  Newspaper,
  Search,
  Settings,
  Swords,
  User,
} from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth, useCurrentHandle } from "../auth";
import { useData } from "../api/context";
import { useMyBots } from "../db/queries";
import { useCurrentFleet } from "../fleets/CurrentFleetProvider";
import Logo from "./Logo";
import { builderPath } from "../lib/paths";
import { UserAvatar } from "./Avatar";
import SearchPalette from "./SearchPalette";
import s from "./TopBar.module.css";

const searchIcon = <Search size={14} strokeWidth={1.5} style={{ flex: "none" }} />;

// same glyph vocabulary as the search palette / old sidebar, sized for pills
const ICONS: Record<string, JSX.Element> = {
  fleet: <Logo size={16} mono />,
  feed: <Newspaper size={21} strokeWidth={1.5} />,
  market: <Globe size={21} strokeWidth={1.5} />,
  build: <FlaskConical size={21} strokeWidth={1.5} />,
  board: <Crown size={21} strokeWidth={1.5} />,
  user: <User size={15} strokeWidth={1.5} />,
  gear: <Settings size={15} strokeWidth={1.5} />,
  out: <LogOut size={15} strokeWidth={1.5} />,
  trophy: <Swords size={21} strokeWidth={1.5} />,
};

export default function TopBar() {
  const nav = useNavigate();
  const loc = useLocation();
  const { user, profile, signOut } = useAuth();
  const handle = useCurrentHandle();
  const live = useData();
  const { currentId } = useCurrentFleet();
  const { data: roster } = useMyBots(user?.id ?? null);
  // telltale: how many open positions does this fleet hold right now?
  const openCount = useMemo(() => {
    const names = new Set(
      (roster ?? [])
        .filter((b) => b.stage === "deployed" && (!currentId || b.fleet_id === currentId))
        .map((b) => b.name),
    );
    return live.bots.reduce((a, b) => a + (names.has(b.name) ? (b.open?.length ?? 0) : 0), 0);
  }, [roster, currentId, live.bots]);
  const inTrade = openCount > 0;
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState(false);
  const [menu, setMenu] = useState(false);

  useEffect(() => { setOpen(false); setMenu(false); }, [loc.pathname]);
  useEffect(() => {
    if (!user) return; // search is a logged-in tool — no palette for visitors
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearch(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [user]);

  // One rule: Fleet is the command center and wears the single dressed-up
  // (labeled) control; every other destination is a badged icon — glyph only,
  // label in the tooltip. The daily surfaces (Feed, Markets, Build) sit left
  // by Fleet; the community surfaces (Leaderboard, Arena) sit right.
  const primary = user
    ? [
        { l: "Feed", p: "/feed", i: "feed" },
        { l: "Markets", p: "/market", i: "market" },
        { l: "Build", p: "/build", i: "build" },
      ]
    : [{ l: "Markets", p: "/market", i: "market" }];
  const secondary = [
    { l: "Leaderboard", p: "/leaderboard", i: "board" },
    { l: "Arena", p: "/challenges", i: "trophy" },
  ];

  const isActive = (p: string) => {
    if (p === "/") return loc.pathname === "/";
    // "/build" must not light up on "/builder/:handle" (profile pages)
    if (p === "/build") return loc.pathname === "/build" || loc.pathname.startsWith("/build/");
    return (
      loc.pathname.startsWith(p) ||
      (p === "/challenges" && loc.pathname.startsWith("/challenge"))
    );
  };

  const go = (p: string) => () => nav(p);

  // bar: badged icon that reveals its name on hover; sheet (mobile): icon + label
  const iconPill = (it: { l: string; p: string; i?: string }) => (
    <button
      key={it.p}
      className={`${s.iconLink} ${isActive(it.p) ? s.active : ""}`}
      onClick={go(it.p)}
      aria-label={it.l}
    >
      {it.i && ICONS[it.i]}
      {/* 0fr→1fr grid track: label animates to its real width on hover */}
      <span className={s.hoverLbl}>
        <span>{it.l}</span>
      </span>
    </button>
  );
  // right cluster (crown = Leaderboard, swords = Arena): same reveal, mirrored —
  // the label grows to the LEFT so the icon sits to the right of the word.
  const iconPillRight = (it: { l: string; p: string; i?: string }) => (
    <button
      key={it.p}
      className={`${s.iconLink} ${isActive(it.p) ? s.active : ""}`}
      onClick={go(it.p)}
      aria-label={it.l}
    >
      <span className={`${s.hoverLbl} ${s.hoverLblRight}`}>
        <span>{it.l}</span>
      </span>
      {it.i && ICONS[it.i]}
    </button>
  );
  const pill = (it: { l: string; p: string; i?: string }) => (
    <button key={it.p} className={`${s.link} ${isActive(it.p) ? s.active : ""}`} onClick={go(it.p)}>
      {it.i && ICONS[it.i]}
      {it.l}
    </button>
  );
  const links = primary.map(iconPill);
  const rightLinks = secondary.map(iconPillRight);
  const sheetLinks = [...primary, ...secondary].map(pill);

  // says nothing at rest — a pulsing telltale; hover/on-station slides the
  // status readout open inside the pill
  const fleetBtn = user ? (
    <button
      className={`${s.fleet} ${isActive("/fleet") ? s.fleetActive : ""}`}
      onClick={go("/fleet")}
      title="Fleet"
      aria-label="Fleet"
    >
      {inTrade ? (
        <svg className={`${s.fleetWave} ${s.fleetWaveOn}`} viewBox="0 0 24 14" aria-hidden>
          <g>
            <path
              d="M0 7 C3 1 3 1 6 7 C9 13 9 13 12 7 C15 1 15 1 18 7 C21 13 21 13 24 7 C27 1 27 1 30 7 C33 13 33 13 36 7"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </g>
        </svg>
      ) : (
        <span className={s.fleetDot} aria-hidden />
      )}
      <span className={`${s.fleetStatus} ${inTrade ? s.fleetStatusOn : ""}`}>
        {inTrade ? `IN TRADE · ${openCount}` : "WATCHING"}
      </span>
    </button>
  ) : null;

  return (
    <header className={s.bar}>
      <div className={s.inner}>
        <button className={s.menuBtn} aria-label="Menu" onClick={() => setOpen((o) => !o)}>
          <Menu size={20} strokeWidth={1.5} />
        </button>

        {fleetBtn}

        <nav className={s.nav}>{links}</nav>

        {/* the brand mark holds the bar's center; the plane dances on hover */}
        <button className={s.brand} onClick={go(user ? "/feed" : "/")} aria-label="Paper Fleet home">
          <Logo size={28} />
        </button>

        <div className={s.right}>
          {/* icons lead the right cluster: their hover-reveal grows leftward into
              the bar's empty center, so the search and avatar never move */}
          <nav className={s.nav}>{rightLinks}</nav>
          {user && (
            <button className={s.searchBar} onClick={() => setSearch(true)} aria-label="Search" title="Search · ⌘K">
              {searchIcon}
              <span className={s.searchPh}>Search</span>
              <kbd className={s.kbd}>⌘K</kbd>
            </button>
          )}
          {user ? (
            <>
              <span className={s.avatarWrap}>
                <span className={s.avatar} title={handle ? `@${handle}` : "Account"} onClick={() => setMenu((m) => !m)}>
                  <UserAvatar
                    handle={handle}
                    name={profile?.display_name}
                    url={profile?.avatar_url}
                    color={profile?.avatar_color || undefined}
                    size={32}
                  />
                </span>
                {menu && (
                  <div className={s.menu} role="menu">
                    <button
                      className={s.menuItem}
                      onClick={() => nav(handle ? builderPath(handle) : "/settings")}
                    >
                      {ICONS.user}
                      Your profile
                    </button>
                    <button className={s.menuItem} onClick={go("/settings")}>{ICONS.gear}Settings</button>
                    <div className={s.menuSep} />
                    <button className={s.menuItem} onClick={() => { setMenu(false); signOut(); }}>{ICONS.out}Log out</button>
                  </div>
                )}
              </span>
            </>
          ) : (
            <button className={s.link} onClick={go("/signin")}>Log in</button>
          )}
        </div>
      </div>

      {open && <div className={s.sheet}>{sheetLinks}</div>}
      {search && <SearchPalette onClose={() => setSearch(false)} />}
    </header>
  );
}
