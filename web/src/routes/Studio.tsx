import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { INDICATORS, MARKETS, isAvailable } from "../data/catalog";
import p from "./pages.module.css";
import s from "./catalog.module.css";

const ENGINE = import.meta.env.VITE_ENGINE_URL as string | undefined;

interface BtStats {
  n: number;
  net_pct_per_trade: number;
  win_rate: number;
  max_drawdown: number;
}

const OPS: [string, string][] = [
  ["ge", "≥"],
  ["le", "≤"],
  ["gt", ">"],
  ["lt", "<"],
  ["crosses_above", "crosses ↑"],
  ["crosses_below", "crosses ↓"],
];

interface Cond {
  ind: string;
  op: string;
  value: string;
}

export default function Studio() {
  const [mkt, setMkt] = useState(0);
  const [side, setSide] = useState<"long" | "short">("short");
  const [name, setName] = useState("my strategy");
  const [conds, setConds] = useState<Cond[]>([
    { ind: "RSI", op: "lt", value: "30" },
  ]);

  const market = MARKETS[mkt];
  const palette = useMemo(
    () => INDICATORS.filter((i) => isAvailable(i, market)),
    [market],
  );

  const spec = useMemo(() => {
    const children = conds
      .filter((c) => c.ind)
      .map((c) => ({
        left: { ind: c.ind },
        op: c.op,
        right: c.value === "" || isNaN(Number(c.value)) ? c.value : Number(c.value),
      }));
    return {
      name,
      side,
      market: market.id,
      entry: { logic: "AND", children },
      exit: { time_bars: 16, stop: { mode: "none", param: 0 } },
      sizing: { risk: 0.0075, notional_cap: 0.2, weight: 1 },
    };
  }, [conds, name, side, market]);

  const set = (i: number, patch: Partial<Cond>) =>
    setConds((cs) => cs.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  const add = () =>
    setConds((cs) => [...cs, { ind: palette[0]?.id ?? "", op: "gt", value: "0" }]);
  const rm = (i: number) => setConds((cs) => cs.filter((_, j) => j !== i));

  const [bt, setBt] = useState<BtStats | null>(null);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function runBacktest() {
    if (!ENGINE) return;
    setRunning(true);
    setErr(null);
    setBt(null);
    try {
      const res = await fetch(`${ENGINE}/v1/backtest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          spec,
          symbols: ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"],
          interval: "15m",
          limit: 1000,
        }),
      });
      const j = await res.json();
      if (!j.ok) throw new Error(j.error || "backtest failed");
      setBt(j.stats as BtStats);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <>
      <div className={p.top}>
        <div>
          <h1 className={p.title}>Strategy Studio</h1>
          <div className={p.subtitle}>
            Compose entry conditions from the indicator palette. The spec on
            the right is exactly what the engine runs — no code.
          </div>
        </div>
      </div>

      <div className={p.body}>
        <div className={s.studio}>
          <div className={s.panel}>
            <div className={s.tools}>
              <Link className={s.toolLink} to="/indicators">
                Indicator palette ↗
              </Link>
              <Link className={s.toolLink} to="/markets">
                Markets ↗
              </Link>
            </div>
            <label className={s.field}>
              <span className={s.flabel}>Name</span>
              <input
                className={s.text}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>

            <div className={s.field}>
              <span className={s.flabel}>Market</span>
              <div className={p.seg}>
                {MARKETS.map((m, i) => (
                  <button
                    key={m.id}
                    className={`${p.segBtn} ${mkt === i ? p.sel : ""}`}
                    onClick={() => setMkt(i)}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
            </div>

            <div className={s.field}>
              <span className={s.flabel}>Side</span>
              <div className={p.seg}>
                {(["short", "long"] as const).map((sd) => (
                  <button
                    key={sd}
                    className={`${p.segBtn} ${side === sd ? p.sel : ""}`}
                    onClick={() => setSide(sd)}
                  >
                    {sd}
                  </button>
                ))}
              </div>
            </div>

            <div className={s.field}>
              <span className={s.flabel}>
                Entry — all of ({palette.length} indicators available)
              </span>
              {conds.map((c, i) => (
                <div key={i} className={s.condRow}>
                  <select
                    className={s.sel}
                    value={c.ind}
                    onChange={(e) => set(i, { ind: e.target.value })}
                  >
                    {palette.map((ind) => (
                      <option key={ind.id} value={ind.id}>
                        {ind.id}
                      </option>
                    ))}
                  </select>
                  <select
                    className={s.selOp}
                    value={c.op}
                    onChange={(e) => set(i, { op: e.target.value })}
                  >
                    {OPS.map(([op, lbl]) => (
                      <option key={op} value={op}>
                        {lbl}
                      </option>
                    ))}
                  </select>
                  <input
                    className={s.val}
                    value={c.value}
                    onChange={(e) => set(i, { value: e.target.value })}
                  />
                  <button
                    className={s.rm}
                    onClick={() => rm(i)}
                    aria-label="Remove condition"
                  >
                    ×
                  </button>
                </div>
              ))}
              <button className={`${p.btn} ${p.sm}`} onClick={add}>
                + condition
              </button>
            </div>
          </div>

          <div className={s.jsonWrap}>
            <div className={s.jsonHead}>strategy spec</div>
            <pre className={s.jsonPre}>{JSON.stringify(spec, null, 2)}</pre>
            <div className={s.btPanel}>
              <button
                className={`${p.btn} ${p.pri} ${p.sm}`}
                onClick={runBacktest}
                disabled={!ENGINE || running}
              >
                {running ? "Running…" : "Run backtest"}
              </button>
              {!ENGINE && (
                <span className={s.jsonNote}>
                  Engine not connected — set VITE_ENGINE_URL
                </span>
              )}
              {err && <span className={s.btErr}>{err}</span>}
              {bt && (
                <div className={s.btStats}>
                  <span>
                    <b>{bt.n}</b> trades
                  </span>
                  <span className={bt.net_pct_per_trade >= 0 ? s.up : s.down}>
                    <b>{bt.net_pct_per_trade.toFixed(2)}%</b>/trade
                  </span>
                  <span>
                    <b>{(bt.win_rate * 100).toFixed(0)}%</b> win
                  </span>
                  <span>
                    <b>{(bt.max_drawdown * 100).toFixed(1)}%</b> dd
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
