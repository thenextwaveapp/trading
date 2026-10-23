import { Fragment } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import r from "./build.module.css";
import { FLOW_PATHS, FLOW_STEPS, withBot } from "./stages";

export default function Steps({ current }: { current: number }) {
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const bot = sp.get("bot");
  return (
    <div className={r.steps}>
      {FLOW_STEPS.map((l, i) => {
        const n = i + 1;
        const done = n < current;
        const now = n === current;
        return (
          <Fragment key={l}>
            {i > 0 && <span className={r.stepLine} />}
            <span
              className={`${r.step} ${now ? r.now : done ? r.done : ""}`}
              onClick={() => done && nav(withBot(FLOW_PATHS[i], bot))}
            >
              {done ? "✓" : n}
            </span>
            {now && <span className={r.stepLabel}>{l}</span>}
          </Fragment>
        );
      })}
    </div>
  );
}
