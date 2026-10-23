import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useData } from "../api/context";
import { identicon, pct } from "../lib/format";
import p from "./pages.module.css";

export default function Landing() {
  const nav = useNavigate();
  const d = useData();

  const top = useMemo(
    () => [...d.variants].sort((a, b) => b.ret - a.ret).slice(0, 8),
    [d.variants],
  );

  return (
    <div className={p.body}>
      <section style={{ maxWidth: 680, padding: "64px 0 36px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--muted)", fontSize: 13, marginBottom: 20 }}>
          <span className="liveDot" /> Live paper trading · the market is the judge
        </div>
        <h1 style={{ fontSize: 52, fontWeight: 600, letterSpacing: "-0.03em", lineHeight: 1.05 }}>
          Build trading bots.<br />Train them. Watch them win.
        </h1>
        <p style={{ color: "var(--muted)", fontSize: 17, lineHeight: 1.6, marginTop: 18, maxWidth: 560 }}>
          Make a bot in plain English, put it through a brutal gym, and deploy the ones that earn it —
          on paper money first, real money when you're ready. Every stat is a verified track record.
        </p>
        <div style={{ display: "flex", gap: 12, marginTop: 28, flexWrap: "wrap" }}>
          <button className={`${p.btn} ${p.pri}`} style={{ height: 48, padding: "0 22px", fontSize: 15 }} onClick={() => nav("/signin")}>
            Start free
          </button>
          <button className={p.btn} style={{ height: 48, padding: "0 22px", fontSize: 15 }} onClick={() => nav("/leaderboard")}>
            Browse the leaderboard
          </button>
        </div>
      </section>

      <section style={{ paddingBottom: 56 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 14 }}>
          <h2 className={p.h2}>Winning right now</h2>
          <span className="lbl lk" onClick={() => nav("/leaderboard")}>live on the leaderboard →</span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(230px,1fr))", gap: 12 }}>
          {top.map((v) => (
            <div key={v.name} className="card" style={{ padding: 16, cursor: "pointer" }} onClick={() => nav("/bot/" + encodeURIComponent(v.name))}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                  <svg width="34" height="34" viewBox="0 0 34 34"><rect width="34" height="34" rx="9" fill="#12161D" /><path d={identicon(v.name, 22)} fill="#3a81d7" transform="translate(6 6)" /></svg>
                  <div style={{ fontWeight: 500 }}>{v.name}</div>
                </div>
                <span className={`num ${v.ret >= 0 ? "up" : "down"}`} style={{ fontSize: 13 }}>{pct(v.ret, true)}</span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
