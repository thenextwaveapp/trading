import { useNavigate } from "react-router-dom";
import { INDICATORS, MARKETS, isAvailable } from "../data/catalog";
import p from "./pages.module.css";
import s from "./catalog.module.css";

const ALL_COLS = ["open", "high", "low", "close", "volume"];

export default function Markets() {
  const nav = useNavigate();
  return (
    <>
      <div className={p.top}>
        <div>
          <h1 className={p.title}>Markets</h1>
          <div className={p.subtitle}>
            One engine, many markets. A market is defined by the data it
            truthfully provides — and that alone decides which indicators are
            computable on it.
          </div>
        </div>
      </div>

      <div className={p.body}>
        <div className={s.mgrid}>
          {MARKETS.map((m) => {
            const avail = INDICATORS.filter((i) => isAvailable(i, m)).length;
            const gated = INDICATORS.length - avail;
            const live = m.asset_class.startsWith("crypto");
            return (
              <div key={m.id} className={s.mcard}>
                <div className={s.mhead}>
                  <span className={s.mname}>{m.label}</span>
                  <span
                    className={`${s.mbadge} ${live ? s.mbadgeLive : ""}`}
                  >
                    {live ? "live" : "planned"}
                  </span>
                </div>
                <div className={s.mkind}>{m.series_kind} series</div>

                <div className={s.mprovLabel}>provides</div>
                <div className={s.chips}>
                  {ALL_COLS.map((c) => {
                    const has = m.provides.includes(c);
                    return (
                      <span
                        key={c}
                        className={`${s.chip} ${has ? "" : s.chipOff}`}
                      >
                        {c}
                      </span>
                    );
                  })}
                </div>

                <div className={s.mcounts}>
                  <div>
                    <div className={s.mcNum}>{avail}</div>
                    <div className={s.mcLbl}>indicators</div>
                  </div>
                  <div>
                    <div className={`${s.mcNum} ${s.gatedNum}`}>{gated}</div>
                    <div className={s.mcLbl}>gated</div>
                  </div>
                </div>

                <button
                  className={`${p.btn} ${p.sm}`}
                  onClick={() => nav("/indicators")}
                >
                  View palette
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
