import { useNavigate } from "react-router-dom";
import { useChallenges } from "../db/queries";
import type { ChallengeStatus, DbChallenge } from "../db/types";
import { CardsSkeleton } from "../components/Skeleton";
import p from "./pages.module.css";
import s from "./Challenges.module.css";

const STATUS_LABEL: Record<ChallengeStatus, string> = {
  draft: "Draft",
  open: "Build window open",
  sealed: "Sealed",
  live: "Live",
  closed: "Closed",
};

const STATUS_CLASS: Record<ChallengeStatus, string> = {
  draft: s.sealed,
  open: s.open,
  sealed: s.sealed,
  live: s.live,
  closed: s.closed,
};

export const JUDGE_LABEL: Record<string, string> = {
  return: "Total return",
  calmar: "Return / drawdown",
  profit_factor: "Profit factor",
  low_drawdown: "Lowest drawdown",
  fewest_trades_positive: "Fewest trades, still green",
  median_distance: "Closest to the median",
};

export function holeSummary(ch: DbChallenge): string {
  const holes = ch.lock_set?.holes ?? [];
  if (!holes.length) return "open build";
  return holes.map((h) => h.split(".").slice(-2).join(".")).join(", ");
}

function fmtWhen(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function Challenges() {
  const nav = useNavigate();
  const { data: challenges, loading } = useChallenges();

  const live = (challenges ?? []).filter((c) => c.status === "live" || c.status === "sealed");
  const open = (challenges ?? []).filter((c) => c.status === "open");
  const closed = (challenges ?? []).filter((c) => c.status === "closed");
  const ordered = [...open, ...live, ...closed];

  return (
    <>
      <div className={p.top}>
        <div>
          <h1 className={p.title}>Challenges</h1>
          <div className={p.subtitle}>
            One spec, one hole. Everyone tunes the same thing, the market votes.
          </div>
        </div>
      </div>

      <div className={p.body}>
        {loading ? (
          <CardsSkeleton cards={6} />
        ) : ordered.length === 0 ? (
          <div className="muted" style={{ padding: "40px 0" }}>
            No challenges yet. Check back when the first prompt drops.
          </div>
        ) : (
          <div className={s.grid}>
            {ordered.map((ch) => (
              <div
                key={ch.id}
                className={`card ${s.chCard}`}
                onClick={() => nav("/challenge/" + encodeURIComponent(ch.slug))}
              >
                <div className={s.chTop}>
                  <div className={s.chTitle}>{ch.title}</div>
                  <span className={`${s.st} ${STATUS_CLASS[ch.status]}`}>
                    {STATUS_LABEL[ch.status]}
                  </span>
                </div>
                {ch.blurb && <div className={s.chBlurb}>{ch.blurb}</div>}
                <div className={s.meta}>
                  <span>Tune <span className={s.hole}>{holeSummary(ch)}</span></span>
                  <span>Judge · {JUDGE_LABEL[ch.judge] ?? ch.judge}</span>
                  {ch.season != null && <span>Season {ch.season}{ch.week != null ? ` · Week ${ch.week}` : ""}</span>}
                  {ch.market_close && <span>Closes {fmtWhen(ch.market_close)}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
