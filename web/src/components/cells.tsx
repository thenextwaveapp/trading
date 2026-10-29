import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useData } from "../api/context";
import p from "../routes/pages.module.css";
import { useCandle } from "./CandleModal";

const navStack: string[] = [];

export function useTrackNav() {
  const loc = useLocation();
  const full = loc.pathname + loc.search;
  useEffect(() => {
    if (navStack[navStack.length - 1] !== full) {
      navStack.push(full);
      if (navStack.length > 50) navStack.shift();
    }
  }, [full]);
}

function labelForPath(fullPath: string): string {
  const path = fullPath.split("?")[0];
  if (path === "/" || path === "/fleet") return "Fleet";
  if (path === "/leaderboard") return "Leaderboard";
  if (path === "/build") return "Build";
  if (path === "/build/compose") return "Compose";
  if (path === "/build/training") return "Training";
  if (path === "/build/trials") return "Trials";
  if (path === "/build/weather") return "Weather";
  if (path === "/build/deploy") return "Deploy";
  if (path === "/build/sweep") return "Sweep";
  if (path.startsWith("/build/report/")) return "Report";
  if (path.startsWith("/bot/")) return decodeURIComponent(path.slice(5)) || "Bot";
  if (path.startsWith("/builder/")) return "@" + decodeURIComponent(path.slice(9));
  if (path === "/builder") return "Builder";
  if (path.startsWith("/settings")) return "Settings";
  return "Back";
}

export function BackBar({
  to,
  label: explicitLabel,
  fallbackPath = "/",
  fallbackLabel = "Fleet",
}: {
  to?: string;
  label?: string;
  fallbackPath?: string;
  fallbackLabel?: string;
}) {
  const nav = useNavigate();
  const loc = useLocation();
  const cur = loc.pathname + loc.search;
  if (to && explicitLabel) {
    return (
      <div className={p.crumb}>
        <span className={p.crumbLink} onClick={() => nav(to)}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M9.5 3.5 5 8l4.5 4.5" stroke="currentColor" strokeWidth="1.5" />
          </svg>
          {explicitLabel}
        </span>
      </div>
    );
  }
  // Find most recent previous entry different from current path (ignoring query-only self-updates)
  let prev: string | null = null;
  for (let i = navStack.length - 1; i >= 0; i--) {
    if (navStack[i].split("?")[0] !== loc.pathname) {
      prev = navStack[i];
      break;
    }
  }
  const label = prev ? labelForPath(prev) : fallbackLabel;
  const onClick = () => {
    if (prev) {
      while (navStack.length > 1 && navStack[navStack.length - 1] !== prev) {
        navStack.pop();
      }
      nav(prev);
    } else if (cur !== fallbackPath) {
      nav(fallbackPath);
    }
  };
  return (
    <div className={p.crumb}>
      <span className={p.crumbLink} onClick={onClick}>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M9.5 3.5 5 8l4.5 4.5" stroke="currentColor" strokeWidth="1.5" />
        </svg>
        {label}
      </span>
    </div>
  );
}

export function BotLink({ name }: { name: string }) {
  const nav = useNavigate();
  return (
    <span className="lk" onClick={() => nav("/bot/" + encodeURIComponent(name))}>
      {name}
    </span>
  );
}

export function Coin(p: {
  ticker: string;
  variant?: string;
  t_sig: number;
  entry: number;
  stop?: number | null;
  tp?: number | null;
  exit_t?: number | null;
  kind?: string | null;
  side?: string | null;
}) {
  const open = useCandle();
  const d = useData();
  const sym =
    d.symbols[p.ticker] ||
    (p.ticker ? (p.ticker.endsWith("USDT") ? p.ticker : `${p.ticker}USDT`) : "");
  const title = `${p.ticker}${p.variant ? " · " + p.variant : ""}${
    p.exit_t ? " (closed " + (p.kind || "") + ")" : " (open)"
  }`;
  return (
    <span
      className="lk num"
      style={{ borderBottom: "1px dashed #3A4250" }}
      onClick={() =>
        open({
          sym,
          title,
          t_sig: p.t_sig,
          entry: p.entry,
          stop: p.stop ?? null,
          tp: p.tp ?? null,
          exit_t: p.exit_t ?? null,
          kind: p.kind ?? null,
          side: p.side ?? null,
        })
      }
    >
      {p.ticker} <span style={{ opacity: 0.6 }}>📈</span>
    </span>
  );
}
