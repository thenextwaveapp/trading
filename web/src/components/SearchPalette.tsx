import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { botColor } from "../lib/brand";
import { identicon } from "../lib/format";
import { useBots, useChallenges, useMarket, usePublicProfiles } from "../db/queries";
import s from "./SearchPalette.module.css";

interface Res {
  id: string;
  label: string;
  sub: string;
  path: string;
  dot: React.ReactNode;
}

const ICONS: Record<string, React.ReactNode> = {
  home: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3">
      <rect x="1.5" y="1.5" width="5" height="5" rx="1" /><rect x="9.5" y="1.5" width="5" height="5" rx="1" />
      <rect x="1.5" y="9.5" width="5" height="5" rx="1" /><rect x="9.5" y="9.5" width="5" height="5" rx="1" />
    </svg>
  ),
  market: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.2">
      <path d="M4 2.5v2M4 10.5v3M12 1.5v3M12 11v1.5" /><rect x="2.5" y="4.5" width="3" height="6" rx=".6" />
      <rect x="10.5" y="4.5" width="3" height="6.5" rx=".6" fill="currentColor" />
    </svg>
  ),
  build: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3">
      <path d="M6 1.8v4L2.6 11.4A1.6 1.6 0 0 0 4 13.9h8a1.6 1.6 0 0 0 1.4-2.5L10 5.8v-4" />
      <path d="M5 1.8h6M4.6 9h6.8" />
    </svg>
  ),
  board: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <path d="M2 14h12" stroke="currentColor" strokeWidth="1.3" />
      <rect x="2.8" y="7" width="2.6" height="5" rx=".5" fill="currentColor" />
      <rect x="6.7" y="3.5" width="2.6" height="8.5" rx=".5" fill="currentColor" />
      <rect x="10.6" y="9" width="2.6" height="3" rx=".5" fill="currentColor" />
    </svg>
  ),
  trophy: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3">
      <path d="M4.5 2h7v3.2a3.5 3.5 0 0 1-7 0V2Z" />
      <path d="M4.5 3H2.6a2 2 0 0 0 2.2 2.6M11.5 3h1.9a2 2 0 0 1-2.2 2.6" strokeWidth="1.1" />
      <path d="M8 8.6V11M5.5 14h5M6.6 11h2.8v3" />
    </svg>
  ),
  gear: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="12" r="3" />
      <path d="M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.5-2.4 1a7 7 0 0 0-1.7-1l-.3-2.5h-4l-.3 2.5a7 7 0 0 0-1.7 1l-2.4-1-2 3.5 2 1.5a7 7 0 0 0 0 2l-2 1.5 2 3.5 2.4-1a7 7 0 0 0 1.7 1l.3 2.5h4l.3-2.5a7 7 0 0 0 1.7-1l2.4 1 2-3.5-2-1.5a7 7 0 0 0 .1-1z" />
    </svg>
  ),
};

const PAGES: { label: string; path: string; icon: string }[] = [
  { label: "Home", path: "/feed", icon: "home" },
  { label: "Fleet", path: "/fleet", icon: "home" },
  { label: "Market", path: "/market", icon: "market" },
  { label: "Build a bot", path: "/build", icon: "build" },
  { label: "Leaderboard", path: "/leaderboard", icon: "board" },
  { label: "Challenges", path: "/challenges", icon: "trophy" },
  { label: "Settings", path: "/settings", icon: "gear" },
];

function ident(seed: string, color: string) {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24">
      <rect width="24" height="24" rx="12" fill="#12161d" />
      <path d={identicon(seed, 14)} fill={color} transform="translate(5 5)" />
    </svg>
  );
}

export default function SearchPalette({ onClose }: { onClose: () => void }) {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: bots } = useBots();
  const { data: challenges } = useChallenges();
  const { data: profiles } = usePublicProfiles();
  const { data: market } = useMarket("crypto");

  useEffect(() => inputRef.current?.focus(), []);
  useEffect(() => setActive(0), [q]);

  const query = q.trim().toLowerCase();

  const groups = useMemo(() => {
    const has = (s: string) => !query || s.toLowerCase().includes(query);
    const take = <T,>(xs: T[]) => xs.slice(0, 6);

    const pages: Res[] = PAGES.filter((p) => has(p.label)).map((p) => ({
      id: "pg:" + p.path, label: p.label, sub: "Page", path: p.path,
      dot: <span className={s.dot} style={{ color: "var(--muted)" }}>{ICONS[p.icon]}</span>,
    }));
    const botRes: Res[] = take((bots ?? []).filter((b) => has(b.name) || has(b.family_slug ?? ""))).map((b) => ({
      id: "bot:" + b.id, label: b.name, sub: "Bot", path: "/bot/" + encodeURIComponent(b.name),
      dot: <span className={s.dot}>{ident(b.name, botColor(b))}</span>,
    }));
    const chRes: Res[] = take((challenges ?? []).filter((c) => has(c.title) || has(c.slug))).map((c) => ({
      id: "ch:" + c.id, label: c.title, sub: "Challenge", path: "/challenge/" + encodeURIComponent(c.slug),
      dot: <span className={s.dot} style={{ color: "var(--muted)" }}>{ICONS.trophy}</span>,
    }));
    const blRes: Res[] = take((profiles ?? []).filter((p) => has(p.handle) || has(p.display_name ?? ""))).map((p) => ({
      id: "bl:" + p.id, label: "@" + p.handle, sub: "Builder", path: "/builder/" + encodeURIComponent(p.handle),
      dot: <span className={s.dot}>{ident("@" + p.handle, p.avatar_color || "#3a81d7")}</span>,
    }));
    const mkRes: Res[] = query
      ? take((market ?? []).filter((m) => has(m.base) || has(m.name ?? "") || has(m.symbol))).map((m) => ({
          id: "mk:" + m.symbol, label: m.name ?? m.base, sub: "Market · " + m.base,
          path: "/market/" + encodeURIComponent(m.symbol),
          dot: <span className={s.dot}>{m.logo ? <img src={m.logo} alt="" /> : null}</span>,
        }))
      : [];

    return [
      ["Pages", pages], ["Bots", botRes], ["Challenges", chRes],
      ["Builders", blRes], ["Market", mkRes],
    ].filter(([, r]) => (r as Res[]).length) as [string, Res[]][];
  }, [query, bots, challenges, profiles, market]);

  const flat = useMemo(() => groups.flatMap(([, r]) => r), [groups]);

  const go = (r: Res) => {
    nav(r.path);
    onClose();
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") return onClose();
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, flat.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    if (e.key === "Enter" && flat[active]) { e.preventDefault(); go(flat[active]); }
  };

  return (
    <div className="ovl" onClick={onClose}>
      <div className={s.wrap} onKeyDown={onKey}>
        <div className={`glass ${s.panel}`} onClick={(e) => e.stopPropagation()}>
          <div className={s.inputRow}>
            <svg width="17" height="17" viewBox="0 0 16 16" fill="none" stroke="currentColor" style={{ color: "var(--muted)" }}>
              <circle cx="7" cy="7" r="5" strokeWidth="1.4" />
              <path d="M11 11l3.5 3.5" strokeWidth="1.4" strokeLinecap="round" />
            </svg>
            <input
              ref={inputRef}
              className={s.input}
              placeholder="Search bots, challenges, builders, coins…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            <span className={s.esc}>esc</span>
          </div>
          <div className={s.results}>
            {flat.length === 0 ? (
              <div className={s.empty}>No matches{q ? ` for “${q}”` : ""}.</div>
            ) : (
              groups.map(([name, rows]) => (
                <div key={name}>
                  <div className={s.group}>{name}</div>
                  {rows.map((r) => {
                    const idx = flat.indexOf(r);
                    return (
                      <div
                        key={r.id}
                        className={`${s.item} ${idx === active ? s.active : ""}`}
                        onMouseEnter={() => setActive(idx)}
                        onClick={() => go(r)}
                      >
                        {r.dot}
                        <span className={s.label}>{r.label}</span>
                        <span className={s.sub}>{r.sub}</span>
                      </div>
                    );
                  })}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
