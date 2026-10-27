import { useNavigate } from "react-router-dom";
import { useData } from "../api/context";
import { useCandle } from "./CandleModal";

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
