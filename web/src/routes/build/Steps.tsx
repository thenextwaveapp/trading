import { Fragment } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useLatestBacktest, useMyBot } from "../../db/queries";
import type { Stage } from "../../db/types";
import r from "./build.module.css";
import { FLOW_PATHS, FLOW_STEPS, withBot } from "./stages";

const STAGE_MAX_DONE: Record<Stage, number> = {
  draft: 1,
  training: 1,
  trials: 3,
  weather: 3,
  ready: 4,
  deployed: 5,
};

export default function Steps({
  current,
  onNavigate,
}: {
  current: number;
  onNavigate?: (targetPath: string, stepIndex: number) => void;
}) {
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const botId = sp.get("bot");
  const { data: bot } = useMyBot(botId);
  const { data: bt } = useLatestBacktest(botId);

  const maxDone = (() => {
    let m = current - 1;
    if (bot) m = Math.max(m, STAGE_MAX_DONE[bot.stage] ?? 1);
    if (bt?.status === "done") m = Math.max(m, 3);
    if (bot?.validated_at || bot?.condition_filter) m = Math.max(m, 4);
    if (bot?.launched_at || bot?.stage === "deployed") m = Math.max(m, 5);
    return m;
  })();

  const go = (i: number) => {
    const n = i + 1;
    if (n === current) return;
    const target = withBot(FLOW_PATHS[i], botId);
    if (onNavigate) {
      onNavigate(target, n);
      return;
    }
    if (botId || n <= maxDone || n < current) {
      nav(target);
    }
  };

  return (
    <div className={r.steps}>
      {FLOW_STEPS.map((l, i) => {
        const n = i + 1;
        const now = n === current;
        const done = !now && n <= maxDone;
        const canClick = !now && (Boolean(botId) || Boolean(onNavigate) || done);
        return (
          <Fragment key={l}>
            {i > 0 && <span className={r.stepLine} />}
            <span
              onClick={() => canClick && go(i)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                cursor: canClick ? "pointer" : "default",
              }}
            >
              <span className={`${r.step} ${now ? r.now : done ? r.done : ""}`}>
                {done ? "✓" : n}
              </span>
              <span
                className={r.stepLabel}
                style={{
                  color: now ? "var(--fg)" : done ? "var(--fg-2)" : canClick ? "var(--muted)" : "var(--muted-3)",
                  fontWeight: now ? 500 : 400,
                }}
              >
                {l}
              </span>
            </span>
          </Fragment>
        );
      })}
    </div>
  );
}
