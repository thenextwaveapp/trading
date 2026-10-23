import { useNavigate } from "react-router-dom";
import p from "../pages.module.css";
import Steps from "./Steps";

/** Shown while the bot + its lifecycle data load. */
export function StepLoading({ step }: { step: number }) {
  return (
    <>
      <div className={p.crumb}><b>Build</b></div>
      <Steps current={step} />
      <div className="muted" style={{ padding: 40 }}>Loading…</div>
    </>
  );
}

/** Shown when the step was opened without a bot to work on. */
export function MissingBot({ step }: { step: number }) {
  const nav = useNavigate();
  return (
    <>
      <div className={p.crumb}>
        <span className="lk" onClick={() => nav("/build")}>Build</span> / <b>No bot</b>
      </div>
      <Steps current={step} />
      <div className={p.body} style={{ paddingTop: 40 }}>
        <div className="muted">
          Pick a bot to work on.{" "}
          <span className="lk" style={{ color: "#8BB4E8" }} onClick={() => nav("/build")}>Back to Build →</span>
        </div>
      </div>
    </>
  );
}
