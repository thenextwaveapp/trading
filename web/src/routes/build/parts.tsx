import { useNavigate, useSearchParams } from "react-router-dom";
import { BackBar } from "../../components/cells";
import p from "../pages.module.css";
import Steps from "./Steps";
import { FLOW_PATHS, FLOW_STEPS, withBot } from "./stages";

/** Shown while the bot + its lifecycle data load. */
export function StepLoading({ step }: { step: number }) {
  const [sp] = useSearchParams();
  const botId = sp.get("bot");
  const prevTo = step > 1 ? withBot(FLOW_PATHS[step - 2], botId) : "/build";
  const prevLabel = step > 1 ? FLOW_STEPS[step - 2] : "Build";
  return (
    <>
      <BackBar to={prevTo} label={prevLabel} />
      <Steps current={step} />
      <div className="muted" style={{ padding: 40 }}>Loading…</div>
    </>
  );
}

/** Shown when the step was opened without a bot to work on. */
export function MissingBot({ step }: { step: number }) {
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const botId = sp.get("bot");
  const prevTo = step > 1 ? withBot(FLOW_PATHS[step - 2], botId) : "/build";
  const prevLabel = step > 1 ? FLOW_STEPS[step - 2] : "Build";
  return (
    <>
      <BackBar to={prevTo} label={prevLabel} />
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
