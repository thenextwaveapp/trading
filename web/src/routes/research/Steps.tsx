import { Fragment } from "react";
import { useNavigate } from "react-router-dom";
import r from "./research.module.css";

const PATHS = ["/research/build", "/research/backtest", "/research/checks", "/research/weather", "/research/graduate"];
const LABELS = ["Strategy", "Backtest", "Validation", "Conditions", "Launch"];

export default function Steps({ current }: { current: number }) {
  const nav = useNavigate();
  return (
    <div className={r.steps}>
      {LABELS.map((l, i) => {
        const n = i + 1;
        const done = n < current;
        const now = n === current;
        return (
          <Fragment key={l}>
            {i > 0 && <span className={r.stepLine} />}
            <span
              className={`${r.step} ${now ? r.now : done ? r.done : ""}`}
              onClick={() => done && nav(PATHS[i])}
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
