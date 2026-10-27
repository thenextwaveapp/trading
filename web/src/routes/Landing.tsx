import { botColor } from "../lib/brand";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useData } from "../api/context";
import { useBots } from "../db/queries";
import type { DbBot } from "../db/types";
import { identicon, pct, usd, windowReturn } from "../lib/format";
import s from "./Landing.module.css";

const STEPS: [string, string, string][] = [
  ["01", "Compose", "Make a bot in plain English. Pick a strategy, tune it, see exactly what it will trade."],
  ["02", "Train", "Run it over years of history. Real returns, win rate and drawdown — all after fees."],
  ["03", "Stress-test", "Beat random entries, survive higher costs and a late fill. Real edge, or it's out."],
  ["04", "Deploy", "The ones that earn it battle live, on the same engine. Real P&L, in the open."],
];

/** Stylized multi-line fleet equity chart — the hero's centerpiece. */
function HeroChart() {
  const A = "16,238 64,224 112,230 160,196 208,204 256,166 304,158 352,112 400,100 460,64";
  const B = "16,256 64,250 112,254 160,232 208,240 256,214 304,220 352,186 400,178 460,140";
  const C = "16,272 64,270 112,264 160,268 208,252 256,258 304,240 352,236 460,206";
  return (
    <div className={s.heroArt}>
      <div className={s.heroArtHead}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <span className="liveDot" /> Fleet equity
        </span>
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
        <path d={`M${A} L460,290 L16,290 Z`} fill="url(#heroFill)" />
        <polyline points={C} fill="none" stroke="#814ec6" strokeWidth="2" strokeLinejoin="round" style={{ filter: "drop-shadow(0 0 6px rgba(129,78,198,.5))" }} />
        <polyline points={B} fill="none" stroke="#cb8315" strokeWidth="2" strokeLinejoin="round" style={{ filter: "drop-shadow(0 0 6px rgba(203,131,21,.45))" }} />
        <polyline points={A} fill="none" stroke="#3a81d7" strokeWidth="2.6" strokeLinejoin="round" style={{ filter: "drop-shadow(0 0 7px rgba(58,129,215,.6))" }} />
        <circle cx="460" cy="64" r="4.5" fill="#fff" />
        <circle cx="460" cy="64" r="9" fill="#3a81d7" opacity="0.3" />
      </svg>
    </div>
  );
}

export default function Landing({ onAuth }: { onAuth: (mode: "signin" | "signup") => void }) {
  const nav = useNavigate();
  const d = useData();
  const { data: bots } = useBots();

  const top = useMemo(() => {
    const byName = new Map(d.variants.map((v) => [v.name, v]));
    return (bots ?? [])
      .map((b) => {
        const v = byName.get(b.name);
        const liveRet = v ? windowReturn(v.curve, 30, d.now) : null;
        return { b, ret: liveRet ?? b.bt ?? null, live: liveRet != null };
      })
      .filter((x): x is { b: DbBot; ret: number; live: boolean } => x.ret != null)
      .sort((a, b) => b.ret - a.ret)
      .slice(0, 6);
  }, [bots, d.variants, d.now]);

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

  const nBots = (bots ?? []).length;
  const STATS: [string, string][] = [
    [String(builders.length || "–"), "builders"],
    [String(nBots || "–"), "bots battling"],
    [d.hero.closed.toLocaleString(), "trades, fees on"],
    ["24/7", "live, always on"],
  ];

  return (
    <div className={s.page}>
      {/* ---------- hero ---------- */}
      <section className={s.hero}>
        <div className={s.heroGlow} />
        <div className={s.heroGlow2} />
        <div className={`${s.inner} ${s.heroInner}`}>
          <div>
            <span className={s.eyebrow}>
              <span className="liveDot" /> Live paper trading · the market is the judge
            </span>
            <h1 className={s.h1}>
              Build trading bots.<br />Train them. Watch them win.
            </h1>
            <p className={s.sub}>
              Make a bot in plain English, train and stress-test it, and deploy the ones that earn it —
              on paper money first, real money when you're ready. Every stat is a verified track record.
            </p>
            <div className={s.ctaRow}>
              <button className={s.btnPri} onClick={() => onAuth("signup")}>Start free</button>
              <button className={s.btnGhost} onClick={() => nav("/leaderboard")}>Browse the leaderboard</button>
            </div>
          </div>
          <HeroChart />
        </div>
      </section>

      {/* ---------- stat strip ---------- */}
      {nBots > 0 && (
        <section className={s.band}>
          <div className={`${s.inner}`} style={{ padding: "40px var(--gutter)" }}>
            <div className={s.stats}>
              {STATS.map(([v, l]) => (
                <div key={l} className={s.stat}>
                  <div className={s.statNum}>{v}</div>
                  <div className={s.statLbl}>{l}</div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ---------- winning now ---------- */}
      {top.length > 0 && (
        <section className={`${s.inner} ${s.section}`}>
          <div className={s.sectionHead} style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 12 }}>
            <div>
              <div className={s.kicker}>Leaderboard</div>
              <h2 className={s.h2}>Winning right now</h2>
            </div>
            <button className={s.btnGhost} style={{ height: 40, padding: "0 16px", fontSize: 14 }} onClick={() => nav("/leaderboard")}>
              See the full board
            </button>
          </div>
          <div className={s.board}>
            {top.map(({ b, ret, live }, i) => (
              <div key={b.id} className={s.boardRow} onClick={() => nav("/bot/" + encodeURIComponent(b.name))}>
                <span className={s.rank}>{i + 1}</span>
                <svg className={s.botIcon} width="34" height="34" viewBox="0 0 34 34"><rect width="34" height="34" rx="9" fill="#0f141b" /><path d={identicon(b.name, 22)} fill={botColor(b)} transform="translate(6 6)" /></svg>
                <span>
                  <span className={s.botName}>{b.name}</span>
                  {b.builder?.handle && <span className={s.botBy}> · @{b.builder.handle}</span>}
                </span>
                <span className={`${s.ret} ${ret >= 0 ? "up" : "down"}`}>
                  {pct(ret, true)}{!live && <span className={s.bt}>bt</span>}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ---------- how it works ---------- */}
      <section className={s.band}>
        <div className={`${s.inner} ${s.section}`}>
          <div className={s.sectionHead}>
            <div className={s.kicker}>The pipeline</div>
            <h2 className={s.h2}>From idea to battle-tested</h2>
          </div>
          <div className={s.steps}>
            {STEPS.map(([n, title, body]) => (
              <div key={n} className={s.step}>
                <div className={s.stepNum}>{n}</div>
                <div className={s.stepTitle}>{title}</div>
                <div className={s.stepBody}>{body}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- command center ---------- */}
      <section className={`${s.inner} ${s.section}`}>
        <div className={s.feature}>
          <div>
            <div className={s.kicker}>Command center</div>
            <h2 className={s.h2}>Command your fleet</h2>
            <p className={s.lede}>
              Every deployed bot, marked to the live price. Open positions, P&amp;L, kill-switches —
              your whole fleet at a glance.
            </p>
            <button className={s.btnGhost} style={{ marginTop: 22, height: 44 }} onClick={() => nav("/fleet")}>
              Open the command center
            </button>
          </div>
          <div className={s.panel}>
            <div className={s.panelStats}>
              <div>
                <div className={s.statLbl}>Open positions</div>
                <div className={s.panelStatNum}>{d.positions.length}</div>
              </div>
              <div>
                <div className={s.statLbl}>Unrealized</div>
                <div className={`${s.panelStatNum} ${d.hero.unreal >= 0 ? "up" : "down"}`}>{usd(d.hero.unreal, true)}</div>
              </div>
              <div>
                <div className={s.statLbl}>Bots live</div>
                <div className={s.panelStatNum}>{d.variants.length}</div>
              </div>
            </div>
            {d.positions.length ? (
              d.positions.slice(0, 4).map((pos) => (
                <div key={pos.variant + pos.ticker + pos.t_sig} className={s.posRow}>
                  <span>
                    <b>{pos.ticker}</b> <span className={pos.side === "short" ? "down" : "up"} style={{ fontSize: 12 }}>{pos.side}</span>
                    <span className="muted" style={{ fontSize: 12 }}> · {pos.variant}</span>
                  </span>
                  <span className={`num ${(pos.upnl ?? 0) >= 0 ? "up" : "down"}`}>{usd(pos.upnl, true)}</span>
                </div>
              ))
            ) : (
              <div className="muted" style={{ fontSize: 13, paddingTop: 12 }}>All bots watching — no open positions right now.</div>
            )}
          </div>
        </div>
      </section>

      {/* ---------- builders ---------- */}
      {builders.length > 0 && (
        <section className={s.band}>
          <div className={`${s.inner} ${s.section}`}>
            <div className={s.sectionHead}>
              <div className={s.kicker}>Community</div>
              <h2 className={s.h2}>Copy the winners. Follow the builders.</h2>
              <p className={s.lede}>Find a bot you like, copy it to your roster, and make it yours.</p>
            </div>
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
          </div>
        </section>
      )}

      {/* ---------- cta band ---------- */}
      <section className={s.ctaBand}>
        <div className={s.ctaGlow} />
        <h2 className={s.ctaTitle}>Build your first bot.</h2>
        <p className={s.ctaSub}>Free to start, on paper money. Flip to real capital only when you're ready.</p>
        <button className={s.btnPri} style={{ position: "relative" }} onClick={() => onAuth("signup")}>Start free</button>
      </section>

      {/* ---------- footer ---------- */}
      <footer className={s.footer}>
        <div className={s.footerInner}>
          <div className={s.footBrandCol}>
            <div className={s.footBrand}>
              <svg width="22" height="22" viewBox="0 0 200 200" fill="none" aria-hidden>
                <path d="M170 30 L30 95 L95 125 L170 30 Z" fill="#E9ECF1" />
                <path d="M170 30 L107 131 L122 170 L137 137 L170 30 Z" fill="#5E8FD8" />
              </svg>
              paper fleet
            </div>
            <p className={s.footBlurb}>
              Build trading bots, train them until they earn it, and deploy the ones that pass — paper money
              first, real money when you flip the switch.
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
    </div>
  );
}
