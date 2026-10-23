import { useNavigate } from "react-router-dom";
import p from "../pages.module.css";
import Steps from "./Steps";

/**
 * Placeholder for backtest / validation / launch steps: the backtest &
 * strategy-authoring engine is not yet wired to the frontend.
 */
export default function EngineStep({
  step,
  title,
  what,
  next,
  nextLabel,
}: {
  step: number;
  title: string;
  what: string;
  next?: string;
  nextLabel?: string;
}) {
  const nav = useNavigate();
  return (
    <>
      <div className={p.crumb}><span className="lk" onClick={() => nav("/build")}>Build</span> / <b>New bot</b></div>
      <Steps current={step} />
      <div className={p.body}>
        <section style={{ paddingTop: 40, maxWidth: 640 }}>
          <h1 className={p.title} style={{ fontSize: 32 }}>{title}</h1>
          <div className={p.subtitle} style={{ marginTop: 10, lineHeight: 1.6 }}>{what}</div>
          <div className="card" style={{ padding: 20, marginTop: 24, display: "flex", gap: 12, alignItems: "center" }}>
            <span className="downDot" style={{ background: "#d29922" }} />
            <div style={{ fontSize: 14, color: "var(--fg-2)" }}>
              This runs the backtest &amp; strategy engine, which lands with the write backend.
              Live bot results are real now on <span className="lk" style={{ color: "#8BB4E8" }} onClick={() => nav("/build")}>Build → Reports</span>.
            </div>
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 24, flexWrap: "wrap" }}>
            <button className={p.btn} onClick={() => nav(-1 as unknown as string)}>Back</button>
            {next && <button className={`${p.btn} ${p.pri}`} onClick={() => nav(next)}>{nextLabel || "Continue"}</button>}
          </div>
        </section>
      </div>
    </>
  );
}
