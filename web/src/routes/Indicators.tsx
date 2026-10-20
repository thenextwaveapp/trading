import { useMemo, useState } from "react";
import {
  INDICATORS,
  MARKETS,
  isAvailable,
  missingCols,
  type Indicator,
} from "../data/catalog";
import p from "./pages.module.css";
import s from "./catalog.module.css";

export default function Indicators() {
  const [mkt, setMkt] = useState(0);
  const [q, setQ] = useState("");
  const market = MARKETS[mkt];

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return INDICATORS.filter(
      (i) =>
        !needle ||
        i.id.toLowerCase().includes(needle) ||
        i.label.toLowerCase().includes(needle),
    );
  }, [q]);

  const availCount = filtered.filter((i) => isAvailable(i, market)).length;
  const gated = filtered.length - availCount;

  const groups = useMemo(() => {
    const g: Record<string, Indicator[]> = {};
    for (const i of filtered) (g[i.category] ??= []).push(i);
    return Object.entries(g).sort((a, b) => b[1].length - a[1].length);
  }, [filtered]);

  return (
    <>
      <div className={p.top}>
        <div>
          <h1 className={p.title}>Indicators</h1>
          <div className={p.subtitle}>
            The full standard library — {INDICATORS.length} indicators from
            TA-Lib plus custom primitives. Compose any into a strategy.
          </div>
        </div>
        <input
          className={p.search}
          placeholder="Search RSI, MACD, wick…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      <div className={p.body}>
        <div className={s.controls}>
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
          <div className={s.statline}>
            <b>{availCount}</b> available{" "}
            {gated > 0 && (
              <>
                · <span className={s.gatedNum}>{gated}</span> not computable on{" "}
                {market.label}
              </>
            )}
          </div>
        </div>

        {groups.map(([cat, inds]) => (
          <section key={cat} className={s.cat}>
            <div className={s.catHead}>
              <span>{cat}</span>
              <span className={s.catCount}>{inds.length}</span>
            </div>
            <div className={s.grid}>
              {inds.map((ind) => {
                const ok = isAvailable(ind, market);
                const miss = ok ? [] : missingCols(ind, market);
                return (
                  <div
                    key={ind.id}
                    className={`${s.card} ${ok ? "" : s.cardOff}`}
                    title={ind.label}
                  >
                    <div className={s.cid}>{ind.id}</div>
                    <div className={s.clabel}>{ind.label}</div>
                    <div className={s.chips}>
                      {ind.params.length === 0 ? (
                        <span className={s.chipMuted}>no params</span>
                      ) : (
                        ind.params.map((pa) => (
                          <span key={pa.name} className={s.chip}>
                            {pa.name} {String(pa.default)}
                          </span>
                        ))
                      )}
                    </div>
                    {!ok && (
                      <div className={s.need}>needs {miss.join(", ")}</div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
