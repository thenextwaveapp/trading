import { botColor } from "../lib/brand";
import Wordmark from "../components/Wordmark";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
  type RefObject,
} from "react";
import { useNavigate } from "react-router-dom";
import { useData } from "../api/context";
import { useBots } from "../db/queries";
import type { DbBot } from "../db/types";
import type { Position, Trade, Bot } from "../api/types";
import { identicon, pct, usd, windowReturn } from "../lib/format";
import s from "./Landing.module.css";

// Fires once when the element first scrolls into view — the engine behind every
// reveal + the stat count-up.
function useInView<T extends HTMLElement>(): [RefObject<T>, boolean] {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return;
    const io = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) { setSeen(true); io.disconnect(); } },
      { threshold: 0.18, rootMargin: "0px 0px -8% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [seen]);
  return [ref, seen];
}

// Tracks a media query — drives the mobile composition (one screen + one
// scroll + sticky CTA) vs the full desktop page.
function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setMatches(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [query]);
  return matches;
}

// Rises its children into place (with a slight de-blur) the first time they
// scroll into view.
function Reveal({ children, delay = 0, className = "" }: { children: ReactNode; delay?: number; className?: string }) {
  const [ref, seen] = useInView<HTMLDivElement>();
  return (
    <div ref={ref} className={`${s.reveal} ${seen ? s.revealed : ""} ${className}`} style={{ transitionDelay: `${delay}ms` }}>
      {children}
    </div>
  );
}

// Word-by-word blur-up headline (the Linear hero treatment): each word rises
// out of a 8px blur on its own small delay.
function Words({ text, from = 0, grad = false }: { text: string; from?: number; grad?: boolean }) {
  return (
    <>
      {text.split(" ").map((w, i) => (
        <span key={i} className={`${s.w} ${grad ? s.wGrad : ""}`} style={{ animationDelay: `${120 + (from + i) * 70}ms` }}>
          {w}
          {" "}
        </span>
      ))}
    </>
  );
}

// Counts a numeric stat up from zero when it enters view. Non-numeric values
// ("24/7") are shown verbatim.
function CountUp({ value }: { value: string }) {
  const [ref, seen] = useInView<HTMLSpanElement>();
  const target = Number(value.replace(/[^0-9.]/g, ""));
  const numeric = /\d/.test(value) && !/[/:]/.test(value) && Number.isFinite(target);
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!seen || !numeric) return;
    let raf = 0;
    const dur = 1100;
    let t0: number | null = null;
    const tick = (t: number) => {
      if (t0 == null) t0 = t;
      const p = Math.min(1, (t - t0) / dur);
      setN(target * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [seen, numeric, target]);
  if (!numeric) return <span ref={ref}>{value}</span>;
  return <span ref={ref}>{Math.round(n).toLocaleString()}</span>;
}

// Writes the cursor position into CSS vars so a card's border can light up
// under the pointer (radial mask on a border-only ::after).
function edgeGlow(e: ReactMouseEvent<HTMLElement>) {
  const r = e.currentTarget.getBoundingClientRect();
  e.currentTarget.style.setProperty("--mx", `${e.clientX - r.left}px`);
  e.currentTarget.style.setProperty("--my", `${e.clientY - r.top}px`);
}

function BotDot({ seed, color, size = 40 }: { seed: string; color: string; size?: number }) {
  const inner = Math.round(size * 0.6);
  const off = Math.round((size - inner) / 2);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flex: "none" }}>
      <rect width={size} height={size} rx={size / 2} fill="#12161D" />
      <path d={identicon(seed, inner)} fill={color} transform={`translate(${off} ${off})`} />
    </svg>
  );
}

/** One rotating spotlight of the fleet, live — an open trade (bot, instrument,
 *  unrealized) when there is one, otherwise a top bot "watching". Cycles every
 *  6s. The P&L shows here only, so nothing is duplicated elsewhere on the card. */
function LiveSpotlight({ positions, trades, bots }: { positions: Position[]; trades: Trade[]; bots: Bot[] }) {
  const byName = useMemo(() => new Map(bots.map((v) => [v.name, v])), [bots]);
  const items = useMemo<{ name: string; color: string; tag: string; sub: ReactNode; right: ReactNode }[]>(() => {
    const colorOf = (n: string) => byName.get(n)?.color || "#3a81d7";
    // Open trades (live paper P&L), recent closed trades (realized), and every
    // other live bot "watching" — the full fleet, shown in random order.
    const open = positions.map((p) => ({
      name: p.bot, color: colorOf(p.bot), tag: "live",
      sub: (<>{p.ticker} <span className={p.side === "short" ? "down" : "up"}>{p.side}</span> <span className="muted">· open</span></>),
      right: <span className={`num ${(p.upnl ?? 0) >= 0 ? "up" : "down"}`}>{usd(p.upnl, true)}</span>,
    }));
    const closed = trades
      .slice()
      .sort((a, b) => (b.exit_t || 0) - (a.exit_t || 0))
      .slice(0, 20)
      .map((t) => ({
        name: t.bot, color: colorOf(t.bot), tag: "closed",
        sub: (<>{t.ticker} <span className={t.side === "short" ? "down" : "up"}>{t.side ?? ""}</span> <span className="muted">· closed</span></>),
        right: <span className={`num ${(t.pnl ?? 0) >= 0 ? "up" : "down"}`}>{usd(t.pnl, true)}</span>,
      }));
    const inTrade = new Set(positions.map((p) => p.bot));
    const watching = bots
      .filter((v) => !inTrade.has(v.name))
      .map((v) => ({
        name: v.name, color: v.color || "#3a81d7", tag: "watch",
        sub: <span className="muted">watching</span>,
        right: <span className={`num ${v.ret >= 0 ? "up" : "down"}`}>{pct(v.ret, true)}</span>,
      }));
    return [...open, ...closed, ...watching];
  }, [positions, trades, bots, byName]);

  const [i, setI] = useState(0);
  useEffect(() => {
    if (items.length <= 1) return;
    const t = setInterval(() => {
      setI((cur) => {
        let n = cur;
        while (n === cur) n = Math.floor(Math.random() * items.length);   // random, no immediate repeat
        return n;
      });
    }, 6000);
    return () => clearInterval(t);
  }, [items.length]);

  if (!items.length) return <div className="muted" style={{ fontSize: 13 }}>No live bots yet.</div>;
  const it = items[i % items.length];
  return (
    <div key={it.name + i} className={s.spot}>
      <BotDot seed={it.name} color={it.color} />
      <div className={s.spotMain}>
        <div className={s.spotName}>{it.name}</div>
        <div className={s.spotSub}>{it.sub}</div>
      </div>
      <div className={s.spotRight}>{it.right}</div>
    </div>
  );
}

/** Full-bleed area sparkline along a tape card's bottom edge. */
function Spark({ curve, up }: { curve: [number, number][]; up: boolean }) {
  const pts = curve.length >= 2 ? curve.slice(-40) : null;
  let line = "0,15 100,15";
  if (pts) {
    const lo = Math.min(...pts.map((p) => p[1]));
    const hi = Math.max(...pts.map((p) => p[1]));
    const span = hi - lo || 1;
    line = pts
      .map((p, i) => `${((i / (pts.length - 1)) * 100).toFixed(1)},${(26 - ((p[1] - lo) / span) * 22).toFixed(1)}`)
      .join(" ");
  }
  const c = up ? "61, 220, 151" : "255, 92, 108";
  return (
    <svg className={s.tapeSpark} viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden>
      <polygon points={`0,30 ${line} 100,30`} fill={`rgba(${c}, 0.1)`} />
      <polyline points={line} fill="none" stroke={`rgb(${c})`} strokeWidth="1.4" strokeLinejoin="round" vectorEffect="non-scaling-stroke" opacity="0.9" />
    </svg>
  );
}

/** Shimmer placeholder for one tape card — same bones as a real .tapeItem so
 *  nothing shifts when live data lands. */
function GhostTapeCard() {
  return (
    <span className={s.tapeItem} aria-hidden>
      <span className={s.tapeTop}>
        <span className={`${s.ghost} ${s.ghostDot}`} />
        <span className={s.ghost} style={{ width: 86, height: 12 }} />
      </span>
      <span className={s.ghost} style={{ width: 112, height: 21, marginTop: 12 }} />
      <span className={s.ghost} style={{ width: 62, height: 10, margin: "8px 0 16px" }} />
    </span>
  );
}

/** Live tape across the hero's foot — real fleet activity as glass cards.
 *  Driven by rAF (not a CSS animation) so hovering eases it to a crawl instead
 *  of freezing it. Two identical halves looped at half-width = seamless. */
function Tape({ positions, trades, bots }: { positions: Position[]; trades: Trade[]; bots: Bot[] }) {
  const byName = useMemo(() => new Map(bots.map((v) => [v.name, v])), [bots]);
  const items = useMemo(() => {
    const colorOf = (n: string) => byName.get(n)?.color || "#3a81d7";
    const curveOf = (n: string) => byName.get(n)?.curve ?? [];
    const out: { key: string; name: string; color: string; ticker: string; status: "live" | "closed"; val: number; fmt: "usd" | "pct"; curve: [number, number][] }[] = [];
    for (const p of positions)
      out.push({ key: "p" + p.bot + p.t_sig, name: p.bot, color: colorOf(p.bot), ticker: p.ticker, status: "live", val: p.upnl ?? 0, fmt: "usd", curve: curveOf(p.bot) });
    const closed = trades.slice().sort((a, b) => (b.exit_t || 0) - (a.exit_t || 0)).slice(0, 14);
    for (const t of closed)
      out.push({ key: "t" + t.bot + t.exit_t, name: t.bot, color: colorOf(t.bot), ticker: t.ticker, status: "closed", val: t.pnl ?? 0, fmt: "usd", curve: curveOf(t.bot) });
    if (out.length < 8)
      for (const b of bots.slice(0, 12))
        out.push({ key: "b" + b.name, name: b.name, color: b.color || "#3a81d7", ticker: "all-time", status: "live", val: b.ret, fmt: "pct", curve: b.curve });
    return out.slice(0, 18);
  }, [positions, trades, bots, byName]);

  const trackRef = useRef<HTMLDivElement>(null);
  const slowed = useRef(false);
  useEffect(() => {
    const el = trackRef.current;
    if (!el || items.length < 4) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let x = 0, v = 1, raf = 0, last = performance.now();
    const SPEED = 46; // px/s at full tilt
    const tick = (t: number) => {
      const dt = Math.min(64, t - last) / 1000;
      last = t;
      const target = slowed.current ? 0.12 : 1;        // ease toward crawl, not a hard stop
      v += (target - v) * Math.min(1, dt * 5);
      x -= SPEED * v * dt;
      const half = el.scrollWidth / 2;
      if (half > 0 && -x >= half) x += half;
      el.style.transform = `translate3d(${x.toFixed(2)}px,0,0)`;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [items.length]);

  if (items.length < 4) {
    // Payload not in yet → ghost cards hold the layout instead of a blank gap.
    const empty = !positions.length && !trades.length && !bots.length;
    if (!empty) return null;
    return (
      <div className={s.tape} aria-hidden>
        <div className={s.tapeTrack}>
          <div className={s.tapeHalf}>
            {Array.from({ length: 8 }, (_, i) => <GhostTapeCard key={i} />)}
          </div>
        </div>
      </div>
    );
  }
  const half = (sfx: string) => (
    <div className={s.tapeHalf} aria-hidden={sfx === "b"}>
      {items.map((it) => (
        <span
          key={sfx + it.key}
          className={s.tapeItem}
          style={{ "--bc": it.color } as CSSProperties}
          onMouseMove={edgeGlow}
        >
          <span className={s.tapeTop}>
            <BotDot seed={it.name} color={it.color} size={22} />
            <span className={s.tapeName}>{it.name}</span>
            <span className={`${s.tapeStatus} ${it.status === "live" ? s.tapeStatusLive : ""}`}>
              {it.status === "live" && <span className="liveDot" />}
              {it.status}
            </span>
          </span>
          <span className={`num ${s.tapeVal} ${it.val >= 0 ? "up" : "down"}`}>
            {it.fmt === "usd" ? usd(it.val, true) : pct(it.val, true)}
          </span>
          <span className={s.tapeSub}>{it.ticker}</span>
          <Spark curve={it.curve} up={it.val >= 0} />
        </span>
      ))}
    </div>
  );
  return (
    <div
      className={s.tape}
      aria-label="Live fleet activity"
      onMouseEnter={() => { slowed.current = true; }}
      onMouseLeave={() => { slowed.current = false; }}
      onTouchStart={() => { slowed.current = true; }}
      onTouchEnd={() => { slowed.current = false; }}
    >
      <div className={s.tapeTrack} ref={trackRef}>
        {half("a")}
        {half("b")}
      </div>
    </div>
  );
}

/** Shimmer placeholder rows for the leaderboard while bots load — same row
 *  skeleton as the real board so the list doesn't jump when data lands. */
function GhostBoard() {
  return (
    <div className={s.board} aria-hidden>
      {Array.from({ length: 5 }, (_, i) => (
        <div key={i} className={s.boardRow} style={{ cursor: "default" }}>
          <span className={s.rank}>{String(i + 1).padStart(2, "0")}</span>
          <span className={`${s.ghost} ${s.ghostIcon}`} />
          <span className={s.ghost} style={{ width: 118 + (i % 3) * 26, height: 13 }} />
          <span className={s.barWrap} />
          <span className={s.ghost} style={{ width: 56, height: 13, marginLeft: "auto" }} />
        </div>
      ))}
    </div>
  );
}

/* Per-step vector vignettes for the pipeline. Stroke-first, drawn in the
   brand's soft blue so they read as blueprints, not clip-art. */
const STEP_ART: ReactNode[] = [
  // 01 Compose — plain-English rule becomes an if/then block
  <svg key="a" viewBox="0 0 132 64" className={s.stepSvg}>
    <rect x="4" y="6" width="124" height="22" rx="5" fill="rgba(94,143,216,.08)" stroke="rgba(94,143,216,.45)" />
    <rect x="12" y="14" width="46" height="6" rx="3" fill="rgba(233,236,241,.5)" />
    <rect x="64" y="14" width="24" height="6" rx="3" fill="rgba(94,143,216,.6)" />
    <path d="M22 28v8" stroke="rgba(94,143,216,.5)" />
    <rect x="4" y="36" width="58" height="22" rx="5" fill="none" stroke="rgba(61,220,151,.5)" />
    <rect x="12" y="44" width="34" height="6" rx="3" fill="rgba(61,220,151,.55)" />
    <rect x="70" y="36" width="58" height="22" rx="5" fill="none" stroke="rgba(255,92,108,.45)" />
    <rect x="78" y="44" width="34" height="6" rx="3" fill="rgba(255,92,108,.5)" />
  </svg>,
  // 02 Train — equity curve over history
  <svg key="b" viewBox="0 0 132 64" className={s.stepSvg}>
    {[16, 32, 48].map((y) => <line key={y} x1="4" y1={y} x2="128" y2={y} stroke="rgba(255,255,255,.06)" />)}
    <path d="M4 54 L24 48 L40 50 L56 40 L72 43 L88 30 L104 24 L128 12 L128 58 L4 58 Z" fill="rgba(58,129,215,.14)" />
    <path d="M4 54 L24 48 L40 50 L56 40 L72 43 L88 30 L104 24 L128 12" fill="none" stroke="#5e8fd8" strokeWidth="2" strokeLinejoin="round" />
    <circle cx="128" cy="12" r="3" fill="#e9ecf1" />
  </svg>,
  // 03 Stress-test — the funnel: a crowd of strategies goes in, one earns
  // its way out the bottom
  <svg key="c" viewBox="0 0 132 64" className={s.stepSvg}>
    <path d="M12 6 H120 L79 36 V48 H53 V36 Z" fill="rgba(94,143,216,.07)" stroke="rgba(94,143,216,.45)" strokeLinejoin="round" />
    <circle cx="34" cy="15" r="3" fill="rgba(139,180,232,.6)" />
    <circle cx="52" cy="22" r="3" fill="rgba(255,92,108,.55)" />
    <circle cx="66" cy="13" r="3" fill="rgba(139,180,232,.6)" />
    <circle cx="81" cy="21" r="3" fill="rgba(203,131,21,.65)" />
    <circle cx="97" cy="14" r="3" fill="rgba(255,92,108,.55)" />
    <circle cx="66" cy="30" r="3" fill="rgba(139,180,232,.6)" />
    <circle cx="66" cy="58" r="3.5" fill="#3ddc97" />
    <circle cx="66" cy="58" r="7" fill="rgba(61,220,151,.22)" />
  </svg>,
  // 04 Deploy — radar ping, live on the same engine
  <svg key="d" viewBox="0 0 132 64" className={s.stepSvg}>
    <circle cx="66" cy="32" r="26" fill="none" stroke="rgba(94,143,216,.22)" />
    <circle cx="66" cy="32" r="16" fill="none" stroke="rgba(94,143,216,.35)" />
    <circle cx="66" cy="32" r="7" fill="none" stroke="rgba(94,143,216,.5)" />
    <circle cx="66" cy="32" r="26" fill="none" stroke="rgba(61,220,151,.5)" className={s.ping} />
    <circle cx="66" cy="32" r="3" fill="#3ddc97" />
    <circle cx="86" cy="18" r="2.5" fill="#e9ecf1" opacity=".8" />
  </svg>,
];

const STEPS: [string, string, string][] = [
  ["01", "Compose", "Make a bot in plain English. Tune the strategy. Preview what it trades."],
  ["02", "Train", "Run it over years of history. Returns, win rate, drawdown — net of fees."],
  ["03", "Stress-test", "Beat random entries, higher costs, late fills. Edge survives. Luck gets cut."],
  ["04", "Deploy", "Survivors battle live on the same engine. P&L in the open."],
];

/** Stylized multi-line fleet equity chart — the hero's centerpiece. The
 *  curves and legend are illustrative strategy archetypes, not real bots. */
function HeroChart() {
  const A = "16,238 64,224 112,230 160,196 208,204 256,166 304,158 352,112 400,100 460,64";
  const B = "16,256 64,250 112,254 160,232 208,240 256,214 304,220 352,186 400,178 460,140";
  const C = "16,272 64,270 112,264 160,268 208,252 256,258 304,240 352,236 460,206";
  const names = [
    { name: "Momentum", color: "#3a81d7" },
    { name: "Breakout", color: "#cb8315" },
    { name: "Mean-revert", color: "#814ec6" },
  ];
  return (
    <div className={s.heroArt} onMouseMove={edgeGlow}>
      <div className={s.heroArtHead}>
        <span>Fleet equity</span>
        <span>last 30 days</span>
      </div>
      <svg viewBox="0 0 476 300" width="100%" role="img" aria-label="Rising fleet equity curves">
        <defs>
          <linearGradient id="heroFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#3a81d7" stopOpacity="0.28" />
            <stop offset="1" stopColor="#3a81d7" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[80, 140, 200, 260].map((y) => (
          <line key={y} x1="16" y1={y} x2="460" y2={y} stroke="var(--line-2)" strokeWidth="1" />
        ))}
        <path className={s.areaIn} d={`M${A} L460,290 L16,290 Z`} fill="url(#heroFill)" />
        <polyline className={s.draw} pathLength={1} points={C} fill="none" stroke="#814ec6" strokeWidth="2" strokeLinejoin="round" style={{ filter: "drop-shadow(0 0 6px rgba(129,78,198,.5))", animationDelay: "0.1s" }} />
        <polyline className={s.draw} pathLength={1} points={B} fill="none" stroke="#cb8315" strokeWidth="2" strokeLinejoin="round" style={{ filter: "drop-shadow(0 0 6px rgba(203,131,21,.45))", animationDelay: "0.25s" }} />
        <polyline className={s.draw} pathLength={1} points={A} fill="none" stroke="#3a81d7" strokeWidth="2.6" strokeLinejoin="round" style={{ filter: "drop-shadow(0 0 7px rgba(58,129,215,.6))", animationDelay: "0.4s" }} />
        <circle cx="460" cy="64" r="4.5" fill="#fff" />
        <circle cx="460" cy="64" r="9" fill="#3a81d7" opacity="0.3" className={s.endPulse} />
      </svg>
      <div className={s.legend}>
        {names.slice(0, 3).map((l) => (
          <span key={l.name} className={s.legendChip}>
            <span className={s.legendDot} style={{ background: l.color }} />
            {l.name}
          </span>
        ))}
      </div>
      {/* floating fill chips — illustrative, styled like real fills */}
      <div className={`${s.floatChip} ${s.floatChipTp}`}>
        <span className="up">▲</span> Take profit · <span className="num up">+2.4%</span>
      </div>
    </div>
  );
}

export default function Landing({ onAuth }: { onAuth: (mode: "signin" | "signup") => void }) {
  const nav = useNavigate();
  const d = useData();
  const { data: bots } = useBots();
  // Mobile gets a different composition, not a shrunk desktop: hero copy +
  // live tape on screen one, the leaderboard as the single proof section,
  // and a sticky thumb-zone CTA. Everything else is desktop furniture.
  const isMobile = useMediaQuery("(max-width: 700px)");
  const botsLoading = bots === undefined;

  // Live returns only — no backtest fallback. The board is real or it's empty.
  const top = useMemo(() => {
    const byName = new Map(d.bots.map((v) => [v.name, v]));
    return (bots ?? [])
      .map((b) => {
        const v = byName.get(b.name);
        return { b, ret: v ? windowReturn(v.curve, 30, d.now) : null };
      })
      .filter((x): x is { b: DbBot; ret: number } => x.ret != null)
      .sort((a, b) => b.ret - a.ret)
      .slice(0, 6);
  }, [bots, d.bots, d.now]);

  const builders = useMemo(() => {
    const m = new Map<string, { handle: string; color: string; bots: number }>();
    for (const b of bots ?? []) {
      const h = b.builder?.handle;
      if (!h) continue;
      const e = m.get(h) ?? { handle: h, color: b.builder?.avatar_color ?? "#3a81d7", bots: 0 };
      e.bots += 1;
      m.set(h, e);
    }
    return [...m.values()].sort((a, b) => b.bots - a.bots);
  }, [bots]);

  const maxRet = useMemo(() => Math.max(1e-9, ...top.map((t) => Math.abs(t.ret))), [top]);

  const nBots = (bots ?? []).length;
  const STATS: [string, string][] = [
    [String(builders.length || "–"), "builders"],
    [String(nBots || "–"), "bots battling"],
    [d.hero.closed.toLocaleString(), "trades · fees on"],
    ["24/7", "live"],
  ];

  return (
    <div className={s.page}>
      {/* ---------- hero ---------- */}
      <section className={s.hero}>
        <div className={s.gridBg} />
        <div className={s.heroGlow} />
        {!isMobile && <div className={s.heroGlow2} />}
        {!isMobile && <div className={s.noise} />}
        {/* mobile has no marketing nav — just a brand row that scrolls away
            with the hero (TopNav is display:none below 700px) */}
        {isMobile && (
          <div className={s.heroTop}>
            <span className={s.heroBrand}>
              <Wordmark height={24} />
            </span>
            <button className={s.heroLogin} onClick={() => onAuth("signin")}>Log in</button>
          </div>
        )}
        <div className={`${s.inner} ${s.heroInner}`}>
          <div className={s.heroCopy}>
            <span className={s.pill}>
              <span className={s.pillInner}>
                <span className="liveDot" /> Live paper trading
              </span>
            </span>
            <h1 className={s.h1}>
              <Words text="The league for" />
              <Words text="trading bots." from={3} grad />
            </h1>
            <p className={s.sub}>
              Build a bot in plain English. Deploy it on paper money and earn your spot on the leaderboard.
            </p>
            {/* on mobile the sticky bar carries the CTA — nothing competes mid-screen */}
            {!isMobile && (
              <div className={s.ctaRow}>
                <button className={s.btnPri} onClick={() => onAuth("signup")}>
                  <span className={s.btnSheen} />
                  Start free
                </button>
                <button className={s.btnGhost} onClick={() => nav("/leaderboard")}>Browse the leaderboard</button>
              </div>
            )}
          </div>
          {!isMobile && <HeroChart />}
        </div>
        {/* progressive blur — the hero melts into the tape with a depth-of-field
            ramp (stacked backdrop-filters, each masked a little lower).
            Desktop only: stacked backdrop-filters wreck mobile GPUs. */}
        {!isMobile && (
        <div className={s.blurStack} aria-hidden>
          {[1, 2, 3, 4, 6, 9].map((b, i) => (
            <div
              key={b}
              className={s.blurLayer}
              style={{
                backdropFilter: `blur(${b}px)`,
                WebkitBackdropFilter: `blur(${b}px)`,
                maskImage: `linear-gradient(to bottom, transparent ${i * 12}%, #000 ${i * 12 + 30}%)`,
                WebkitMaskImage: `linear-gradient(to bottom, transparent ${i * 12}%, #000 ${i * 12 + 30}%)`,
              }}
            />
          ))}
        </div>
        )}
        {/* live tape — real fleet activity as glass cards gliding across the
            hero's foot, over the blur band. On mobile it IS the hero art. */}
        <Tape positions={d.positions} trades={d.trades} bots={d.bots} />
      </section>

      {/* ---------- stat strip ---------- */}
      {!isMobile && nBots > 0 && (
        <section className={s.band}>
          <div className={`${s.inner}`} style={{ padding: "48px var(--gutter)" }}>
            <Reveal>
              <div className={s.stats}>
                {STATS.map(([v, l]) => (
                  <div key={l} className={s.stat}>
                    <div className={s.statNum}><CountUp value={v} /></div>
                    <div className={s.statLbl}>{l}</div>
                  </div>
                ))}
              </div>
            </Reveal>
          </div>
        </section>
      )}

      {/* ---------- winning now ---------- */}
      {(botsLoading || top.length > 0) && (
        <section className={`${s.inner} ${s.section}`}>
          <Reveal>
          <div className={s.sectionHead} style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 12 }}>
            <div>
              <div className={s.kicker}>Leaderboard</div>
              <h2 className={s.h2}>Winning right now</h2>
            </div>
            <button className={s.btnGhost} style={{ height: 40, padding: "0 16px", fontSize: 14 }} onClick={() => nav("/leaderboard")}>
              See the full board
            </button>
          </div>
          </Reveal>
          <Reveal delay={100}>
          {botsLoading ? <GhostBoard /> : (
          <div className={s.board}>
            {top.map(({ b, ret }, i) => (
              <div key={b.id} className={s.boardRow} onClick={() => nav("/bot/" + encodeURIComponent(b.name))}>
                <span className={`${s.rank} ${i === 0 ? s.rankTop : ""}`}>{String(i + 1).padStart(2, "0")}</span>
                <svg className={s.botIcon} width="34" height="34" viewBox="0 0 34 34"><rect width="34" height="34" rx="17" fill="#0f141b" /><path d={identicon(b.name, 22)} fill={botColor(b)} transform="translate(6 6)" /></svg>
                <span className={s.boardName}>
                  <span className={s.botName}>{b.name}</span>
                  {b.builder?.handle && <span className={s.botBy}> · @{b.builder.handle}</span>}
                </span>
                <span className={s.barWrap} aria-hidden>
                  <span
                    className={`${s.bar} ${ret >= 0 ? s.barUp : s.barDown}`}
                    style={{ width: `${Math.max(4, (Math.abs(ret) / maxRet) * 100)}%` }}
                  />
                </span>
                <span className={`${s.ret} ${ret >= 0 ? "up" : "down"}`}>
                  {pct(ret, true)}
                </span>
                <span className={s.rowArrow} aria-hidden>→</span>
              </div>
            ))}
          </div>
          )}
          </Reveal>
        </section>
      )}

      {/* ---------- command center ---------- */}
      {!isMobile && (
      <section className={`${s.inner} ${s.section}`}>
        <Reveal>
        <div className={s.feature}>
          <div>
            <div className={s.kicker}>Command center</div>
            <h2 className={s.h2}>Command your fleet</h2>
            <p className={s.lede}>
              The fleet marked to the live price. Positions, P&amp;L, kill switches at a glance.
            </p>
            <button className={s.btnGhost} style={{ marginTop: 22, height: 44 }} onClick={() => nav("/fleet")}>
              Open the command center
            </button>
          </div>
          <div className={s.panel} onMouseMove={edgeGlow}>
            <div className={s.liveHead}>
              <span className={s.liveDot} />
              Live fleet · marked to price
            </div>
            <LiveSpotlight positions={d.positions} trades={d.trades} bots={d.bots} />
            <div className={s.liveFoot}>
              <span><b>{d.positions.length}</b> open position{d.positions.length === 1 ? "" : "s"}</span>
              <span className={s.footSep}>·</span>
              <span><b>{d.bots.length}</b> bots live</span>
              {d.positions.length > 1 && (
                <>
                  <span className={s.footSep}>·</span>
                  <span className={d.hero.unreal >= 0 ? "up" : "down"}>{usd(d.hero.unreal, true)} total</span>
                </>
              )}
            </div>
          </div>
        </div>
        </Reveal>
      </section>
      )}

      {/* ---------- how it works ---------- */}
      {!isMobile && (
      <section className={s.band}>
        <div className={`${s.inner} ${s.section}`}>
          <Reveal>
          <div className={s.sectionHead}>
            <div className={s.kicker}>The pipeline</div>
            <h2 className={s.h2}>From idea to battle-tested</h2>
          </div>
          </Reveal>
          <Reveal delay={100}>
          <div className={s.steps}>
            {STEPS.map(([n, title, body], i) => (
              <div key={n} className={s.step} onMouseMove={edgeGlow}>
                <div className={s.stepArt}>{STEP_ART[i]}</div>
                <div className={s.stepNum}>{n}</div>
                <div className={s.stepTitle}>{title}</div>
                <div className={s.stepBody}>{body}</div>
              </div>
            ))}
          </div>
          </Reveal>
        </div>
      </section>
      )}

      {/* ---------- builders ---------- */}
      {!isMobile && builders.length > 0 && (
        <section>
          <div className={`${s.inner} ${s.section}`}>
            <Reveal>
            <div className={s.sectionHead}>
              <div className={s.kicker}>Community</div>
              <h2 className={s.h2}>Copy the winners. Follow the builders.</h2>
              <p className={s.lede}>Find a bot you like, copy it to your roster, make it yours.</p>
            </div>
            </Reveal>
            <Reveal delay={100}>
            <div className={s.builders}>
              {builders.slice(0, 7).map((b) => (
                <div key={b.handle} className={s.builder} onClick={() => nav("/builder/" + b.handle)}>
                  <svg className={s.avatar} width="46" height="46" viewBox="0 0 46 46"><path d={identicon("@" + b.handle, 30)} fill={b.color} transform="translate(8 8)" /></svg>
                  <span>
                    <div className={s.builderName}>@{b.handle}</div>
                    <div className={s.builderSub}>{b.bots} bot{b.bots === 1 ? "" : "s"}</div>
                  </span>
                </div>
              ))}
            </div>
            </Reveal>
          </div>
        </section>
      )}

      {/* ---------- cta band ---------- */}
      {!isMobile && (
      <section className={s.ctaBand}>
        <div className={s.ctaGlow} />
        <div className={s.noise} />
        <Reveal>
          <h2 className={s.ctaTitle}>Make your first move.</h2>
          <p className={s.ctaSub}>Build a bot tonight, watch it trade tomorrow. Paper money until it proves itself.</p>
          <button className={s.btnPri} style={{ position: "relative" }} onClick={() => onAuth("signup")}>
            <span className={s.btnSheen} />
            Start free
          </button>
          <div className={s.ctaNote} style={{ textAlign: "center" }}>Free forever · no credit card</div>
        </Reveal>
      </section>
      )}

      {/* ---------- footer ---------- */}
      <footer className={s.footer}>
        <div className={s.footerInner}>
          <div className={s.footBrandCol}>
            <div className={s.footBrand}>
              <Wordmark height={24} />
            </div>
            <p className={s.footBlurb}>
              Build trading bots, train them, deploy the ones that pass. Paper money first,
              real money when you flip the switch.
            </p>
          </div>
          <div>
            <div className={s.footColHead}>Product</div>
            <button className={s.footLink} onClick={() => nav("/leaderboard")}>Leaderboard</button>
            <button className={s.footLink} onClick={() => onAuth("signup")}>Start free</button>
            <button className={s.footLink} onClick={() => onAuth("signin")}>Sign in</button>
          </div>
          <div>
            <div className={s.footColHead}>Company</div>
            <button className={s.footLink} onClick={() => nav("/privacy")}>Privacy</button>
          </div>
        </div>
        <div className={s.footBottom}>
          <span>© 2026 Paper Fleet</span>
          <span>Paper money only. Not investment advice.</span>
        </div>
      </footer>

      {/* ---------- mobile sticky CTA — lives in the thumb zone, always ---------- */}
      {isMobile && (
        <div className={s.stickyBar}>
          <button className={`${s.btnPri} ${s.stickyBtn}`} onClick={() => onAuth("signup")}>
            <span className={s.btnSheen} />
            Start free
          </button>
        </div>
      )}
    </div>
  );
}
