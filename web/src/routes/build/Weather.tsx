import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../auth";
import { setConditionFilter, useBuildData, useMyBots } from "../../db/queries";
import type { DbCondition } from "../../db/types";
import { pct } from "../../lib/format";
import p from "../pages.module.css";
import r from "./build.module.css";
import Steps from "./Steps";
import { MissingBot, StepLoading } from "./parts";
import { withBot } from "./stages";

const VOLS = [
  { key: "low", label: "Low volatility" },
  { key: "normal", label: "Normal" },
  { key: "high", label: "High volatility" },
] as const;
const TRENDS = [
  { key: "falling", label: "Bitcoin falling" },
  { key: "flat", label: "Bitcoin flat" },
  { key: "rising", label: "Bitcoin rising" },
] as const;

const cellKey = (vol: string, trend: string) => `${vol}:${trend}`;

export default function Weather() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [sp] = useSearchParams();
  const name = sp.get("bot") ?? "";
  const { data: bots, loading: botsLoading } = useMyBots(user?.id ?? null);
  const bot = bots?.find((b) => b.name === name) ?? null;
  const { loading, backtest, checks, conditions } = useBuildData(bot?.id ?? null);

  const [restrict, setRestrict] = useState(false);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [seeded, setSeeded] = useState(false);

  const byCell = useMemo(() => {
    const m = new Map<string, DbCondition>();
    for (const c of conditions) m.set(cellKey(c.volatility, c.btc_trend), c);
    return m;
  }, [conditions]);

  // Seed the gate once: from the bot's saved filter, else from the winning cells.
  useEffect(() => {
    if (seeded || !bot) return;
    const saved = (bot.condition_filter ?? null) as { restrict?: boolean; cells?: string[] } | null;
    if (saved?.cells) {
      setRestrict(!!saved.restrict);
      setSel(new Set(saved.cells));
      setSeeded(true);
    } else if (conditions.length) {
      setSel(new Set(conditions.filter((c) => (c.return_per_trade ?? 0) > 0).map((c) => cellKey(c.volatility, c.btc_trend))));
      setSeeded(true);
    }
  }, [bot, conditions, seeded]);

  if (botsLoading || (bot && loading)) return <StepLoading step={4} />;
  if (!bot) return <MissingBot step={4} />;

  const persist = (next: Set<string>, nextRestrict: boolean) => {
    if (!bot) return;
    setConditionFilter(bot.id, nextRestrict ? { restrict: true, cells: [...next] } : null);
  };
  const toggleCell = (k: string) => {
    const next = new Set(sel);
    next.has(k) ? next.delete(k) : next.add(k);
    setSel(next);
    if (restrict) persist(next, true);
  };
  const toggleRestrict = () => {
    const next = !restrict;
    setRestrict(next);
    persist(sel, next);
  };

  const inScope = (c: DbCondition) => !restrict || sel.has(cellKey(c.volatility, c.btc_trend));
  const all = summarise(conditions);
  const selected = summarise(conditions.filter(inScope));
  const passed = checks.filter((c) => c.status === "pass").length;
  const ready = checks.length > 0 && passed === checks.length;
  const noConditions = !backtest || conditions.length === 0;

  return (
    <>
      <div className={p.crumb}>
        <span className="lk" onClick={() => nav("/build")}>Build</span> / <b>{name}</b>
      </div>
      <Steps current={4} />
      <div className={p.body}>
        <section style={{ padding: "32px 0 24px" }}>
          <h1 className={p.title} style={{ fontSize: 34 }}>Market conditions</h1>
          <div className={p.subtitle} style={{ marginTop: 8 }}>Performance by Bitcoin trend and market volatility.</div>
        </section>

        {noConditions ? (
          <div className={r.statusCard}>
            <span className="downDot" style={{ background: "#d29922" }} />
            <div>
              <div style={{ fontSize: 15, fontWeight: 500 }}>No conditions breakdown yet.</div>
              <div className="lbl" style={{ marginTop: 4 }}>It's computed from the backtest — finish training and the trials first.</div>
              <button className={`${p.btn} ${p.pri}`} style={{ marginTop: 14 }} onClick={() => nav(withBot("/build/training", name))}>Go to training</button>
            </div>
          </div>
        ) : (
          <section style={{ display: "flex", flexWrap: "wrap", gap: 24, alignItems: "flex-start" }}>
            <div style={{ flex: "999 1 520px", minWidth: 0 }}>
              <div className={r.wgrid}>
                <div />
                {TRENDS.map((t) => <div key={t.key} className={r.wColHead}>{t.label}</div>)}
                {VOLS.map((v) => (
                  <WeatherRow key={v.key} label={v.label} vol={v.key} byCell={byCell} restrict={restrict} sel={sel} onToggle={toggleCell} />
                ))}
              </div>
            </div>

            <div style={{ flex: "1 1 300px", minWidth: 0, display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="card" style={{ padding: 18, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 500 }}>Restrict to selected</div>
                  <div className="lbl" style={{ marginTop: 3, lineHeight: 1.4 }}>Skip trades outside the chosen cells.</div>
                </div>
                <button className={`${r.toggle} ${restrict ? r.toggleOn : ""}`} onClick={toggleRestrict} aria-pressed={restrict}><span /></button>
              </div>
              <div className="card" style={{ padding: 0, overflow: "hidden" }}>
                <div className={r.cmpRow}>
                  <Cmp label="All conditions" ret={all.ret} trades={all.trades} />
                  <Cmp label="Selected only" ret={selected.ret} trades={selected.trades} dim={!restrict} />
                </div>
              </div>
            </div>
          </section>
        )}

        <section className={r.verdict}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="lbl">Verdict</div>
            <div style={{ fontSize: 22, fontWeight: 500, marginTop: 4 }}>
              {ready ? `${name} is ready to launch.` : "Keep testing before launch."}
            </div>
            <div className="lbl" style={{ marginTop: 4 }}>
              {checks.length ? `${passed} of ${checks.length} trials passed` : "trials not run"}
              {restrict && sel.size ? ` · ${sel.size} condition${sel.size > 1 ? "s" : ""} only` : ""}
            </div>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button className={p.btn} onClick={() => nav("/build")}>Later</button>
            <button className={`${p.btn} ${p.pri}`} disabled={!ready} onClick={() => nav(withBot("/build/deploy", name))}>Deploy bot</button>
          </div>
        </section>
      </div>
    </>
  );
}

function WeatherRow({ label, vol, byCell, restrict, sel, onToggle }: {
  label: string; vol: string; byCell: Map<string, DbCondition>; restrict: boolean; sel: Set<string>; onToggle: (k: string) => void;
}) {
  return (
    <>
      <div className={r.wRowHead}>{label}</div>
      {TRENDS.map((t) => {
        const k = cellKey(vol, t.key);
        const c = byCell.get(k);
        const ret = c?.return_per_trade ?? null;
        const pos = (ret ?? 0) >= 0;
        const on = restrict && sel.has(k);
        return (
          <button
            key={t.key}
            className={`${r.wCell} ${ret == null ? "" : pos ? r.wPos : r.wNeg} ${on ? r.wOn : ""}`}
            onClick={() => c && onToggle(k)}
            disabled={!c}
          >
            <span className={`num ${pos ? "up" : "down"}`} style={{ fontSize: 17 }}>{ret == null ? "–" : pct(ret, true)}</span>
            <span className="lbl" style={{ marginTop: 3 }}>
              {c ? `per trade · ${c.trades ?? 0} trades` : "no trades"}
              {c?.is_current && <span className={r.wCur}> · now</span>}
            </span>
          </button>
        );
      })}
    </>
  );
}

function Cmp({ label, ret, trades, dim }: { label: string; ret: number | null; trades: number; dim?: boolean }) {
  return (
    <div style={{ padding: "16px 18px", opacity: dim ? 0.5 : 1 }}>
      <div className="lbl">{label}</div>
      <div className={`num ${(ret ?? 0) >= 0 ? "up" : "down"}`} style={{ fontSize: 24, marginTop: 4 }}>{ret == null ? "–" : pct(ret, true)}</div>
      <div className="lbl num" style={{ marginTop: 2 }}>{trades} trades</div>
    </div>
  );
}

// Trade-weighted average return across a set of condition cells.
function summarise(cs: DbCondition[]): { ret: number | null; trades: number } {
  let trades = 0, weighted = 0;
  for (const c of cs) {
    const n = c.trades ?? 0;
    trades += n;
    weighted += (c.return_per_trade ?? 0) * n;
  }
  return { ret: trades ? weighted / trades : null, trades };
}
