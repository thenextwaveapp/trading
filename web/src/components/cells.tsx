import { useEffect } from "react";
import { ArrowLeft } from "lucide-react";
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
  if (path === "/build") return "Lab";
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
  // canonical readable paths: /@handle, /@handle/bot-slug, /@handle/slug/TICKER
  if (path.startsWith("/@")) {
    const seg = path.slice(1).split("/");
    if (seg.length >= 3) return seg[2]; // the ticker on a trade page
    if (seg.length === 2) return seg[1]; // the bot slug
    return seg[0]; // @handle
  }
  if (path.startsWith("/settings")) return "Settings";
  return "Back";
}

export function BackBar({
  to,
  label: explicitLabel,
  fallbackPath = "/",
  fallbackLabel = "Fleet",
  bare = false,
}: {
  to?: string;
  label?: string;
  fallbackPath?: string;
  fallbackLabel?: string;
  /** render just the arrow button (no row wrapper) so it can sit inside a
   *  page header — on phones this keeps the back control from eating a row */
  bare?: boolean;
}) {
  const nav = useNavigate();
  const loc = useLocation();
  const cur = loc.pathname + loc.search;

  // Most recent previous entry whose path differs from here (query-only
  // self-updates don't count as a place to go back to).
  let prev: string | null = null;
  if (!(to && explicitLabel)) {
    for (let i = navStack.length - 1; i >= 0; i--) {
      if (navStack[i].split("?")[0] !== loc.pathname) {
        prev = navStack[i];
        break;
      }
    }
  }
  const label = to && explicitLabel ? explicitLabel : prev ? labelForPath(prev) : fallbackLabel;
  const onClick = () => {
    if (to && explicitLabel) {
      nav(to);
    } else if (prev) {
      while (navStack.length > 1 && navStack[navStack.length - 1] !== prev) {
        navStack.pop();
      }
      nav(prev);
    } else if (cur !== fallbackPath) {
      nav(fallbackPath);
    }
  };

  const btn = (
    <button className={p.backBtn} onClick={onClick} aria-label={`Back to ${label}`}>
      <ArrowLeft size={20} strokeWidth={1.75} />
    </button>
  );
  return bare ? btn : <div className={p.crumb}>{btn}</div>;
}

export function BotLink({ name }: { name: string }) {
  const nav = useNavigate();
  return (
    <span className="lk" onClick={() => nav("/bot/" + encodeURIComponent(name))}>
      {name}
    </span>
  );
}

export function Instrument(p: {
  ticker: string;
  bot?: string;
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
  const title = `${p.ticker}${p.bot ? " · " + p.bot : ""}${
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
