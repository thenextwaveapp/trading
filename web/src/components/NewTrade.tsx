import { useMemo, useState } from "react";
import type { DbMarketRow } from "../db/types";
import { ensureManualBot, queueOpenTrade, useMarket } from "../db/queries";
import { pct, usd } from "../lib/format";
import Drawer from "./Drawer";

const inputStyle: React.CSSProperties = {
  height: 42, width: "100%", padding: "0 12px", borderRadius: "var(--radius-sm)",
  border: "1px solid var(--border)", background: "#0d1117", color: "var(--fg)",
  font: "inherit", fontSize: 14,
};

/** Hand-enter a trade on the user's "manual" account: pick an instrument (live
 *  price, like Market), set direction + size + optional exits (the ticket feel
 *  of Compose), and queue an 'open' action the engine fills within seconds. */
export default function NewTrade({
  owner, onClose, onPlaced,
}: {
  owner: string; onClose: () => void; onPlaced?: (ticker: string) => void;
}) {
  const marketName = "crypto";
  const { data: market, loading } = useMarket(marketName);
  const [query, setQuery] = useState("");
  const [sel, setSel] = useState<DbMarketRow | null>(null);
  const [side, setSide] = useState<1 | -1>(1);
  const [size, setSize] = useState("");
  const [stop, setStop] = useState("");
  const [tp, setTp] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const matches = useMemo(() => {
    const rows = market ?? [];
    const q = query.trim().toUpperCase();
    const hit = q
      ? rows.filter((r) => r.base.toUpperCase().includes(q) ||
          (r.name ?? "").toUpperCase().includes(q))
      : rows;
    return hit.slice(0, 8);
  }, [market, query]);

  const notional = Number(size) || 0;
  const price = sel?.price ?? null;
  const qty = price && notional > 0 ? notional / price : null;
  const stopPct = price && stop !== "" ? (Number(stop) / price - 1) * 100 : null;
  const canPlace = !!sel && price != null && notional > 0 && !busy;

  const place = async () => {
    if (!canPlace || !sel) return;
    setBusy(true);
    setErr(null);
    try {
      const bot_id = await ensureManualBot(owner);
      const { error } = await queueOpenTrade({
        bot_id,
        ticker: sel.base,
        symbol: sel.symbol,
        side,
        notional,
        stop: stop !== "" ? Number(stop) : null,
        tp: tp !== "" ? Number(tp) : null,
      });
      if (error) throw error;
      onPlaced?.(sel.base);
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't place the trade.");
      setBusy(false);
    }
  };

  const dirBtn = (v: 1 | -1, label: string, color: string) => (
    <button
      type="button"
      onClick={() => setSide(v)}
      style={{
        flex: 1, height: 40, borderRadius: "var(--radius-sm)", cursor: "pointer",
        font: "inherit", fontSize: 14, fontWeight: 600,
        border: `1px solid ${side === v ? color : "var(--line)"}`,
        color: side === v ? color : "var(--muted)",
        background: side === v ? `color-mix(in srgb, ${color} 15%, transparent)` : "transparent",
      }}
    >
      {label}
    </button>
  );

  const footer = (
    <button
      className="btn"
      disabled={!canPlace}
      onClick={() => void place()}
      style={{
        width: "100%", height: 44, justifyContent: "center", fontWeight: 600,
        borderColor: "color-mix(in srgb, var(--up) 55%, transparent)",
        color: "var(--up)",
        background: "color-mix(in srgb, var(--up) 15%, transparent)",
        opacity: canPlace ? 1 : 0.45,
      }}
    >
      {busy ? "Placing…" : sel ? `Place ${side === 1 ? "long" : "short"} · ${usd(notional)}` : "Place trade"}
    </button>
  );

  return (
    <Drawer title="New trade" onClose={onClose} footer={footer}>
      {/* instrument picker — live price, like Market */}
      {!sel ? (
        <>
          <span className="lbl" style={{ display: "block", marginBottom: 6 }}>Instrument</span>
          <input
            style={inputStyle}
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`Search ${marketName}…`}
          />
          <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 2 }}>
            {loading && <div className="muted" style={{ fontSize: 13, padding: "8px 2px" }}>Loading market…</div>}
            {!loading && matches.length === 0 && (
              <div className="muted" style={{ fontSize: 13, padding: "8px 2px" }}>No match.</div>
            )}
            {matches.map((r) => (
              <button
                key={r.symbol}
                onClick={() => { setSel(r); setStop(""); setTp(""); }}
                style={{
                  display: "flex", alignItems: "center", gap: 10, width: "100%",
                  padding: "9px 10px", borderRadius: "var(--radius-sm)", border: "none",
                  background: "transparent", color: "var(--fg)", cursor: "pointer",
                  font: "inherit", textAlign: "left",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--surface-2, rgba(255,255,255,0.05))")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              >
                {r.logo && <img src={r.logo} alt="" width={22} height={22} style={{ borderRadius: "50%" }} />}
                <span style={{ fontWeight: 600 }}>{r.base}</span>
                <span className="muted" style={{ fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.name}</span>
                <span className="num" style={{ marginLeft: "auto" }}>{r.price != null ? usd(r.price) : "—"}</span>
                <span className={`num ${(r.change_pct ?? 0) >= 0 ? "up" : "down"}`} style={{ fontSize: 12, width: 56, textAlign: "right" }}>
                  {pct(r.change_pct, true)}
                </span>
              </button>
            ))}
          </div>
        </>
      ) : (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 18 }}>
            {sel.logo && <img src={sel.logo} alt="" width={28} height={28} style={{ borderRadius: "50%" }} />}
            <span style={{ fontSize: 22, fontWeight: 600 }}>{sel.base}</span>
            <span className="num" style={{ fontSize: 16 }}>{price != null ? usd(price) : "—"}</span>
            <span className={`num ${(sel.change_pct ?? 0) >= 0 ? "up" : "down"}`} style={{ fontSize: 12 }}>{pct(sel.change_pct, true)}</span>
            <button className="btn" style={{ marginLeft: "auto", height: 30 }} onClick={() => setSel(null)}>Change</button>
          </div>

          {/* direction */}
          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            {dirBtn(1, "Long", "var(--up)")}
            {dirBtn(-1, "Short", "var(--down)")}
          </div>

          {/* size */}
          <label style={{ display: "block", marginBottom: 14 }}>
            <span className="lbl" style={{ display: "block", marginBottom: 6 }}>Size (USD)</span>
            <input style={inputStyle} inputMode="decimal" value={size} onChange={(e) => setSize(e.target.value)} placeholder="e.g. 500" />
          </label>

          {/* optional exits — same inputs as Manage position */}
          <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
            <label style={{ flex: 1 }}>
              <span className="lbl" style={{ display: "block", marginBottom: 6 }}>Stop (price)</span>
              <input style={inputStyle} inputMode="decimal" value={stop} onChange={(e) => setStop(e.target.value)} placeholder="Optional" />
            </label>
            <label style={{ flex: 1 }}>
              <span className="lbl" style={{ display: "block", marginBottom: 6 }}>Take profit</span>
              <input style={inputStyle} inputMode="decimal" value={tp} onChange={(e) => setTp(e.target.value)} placeholder="Optional" />
            </label>
          </div>

          {/* live summary */}
          <div style={{ padding: "11px 12px", borderRadius: "var(--radius-sm)", background: "color-mix(in srgb, var(--up) 7%, transparent)", border: "1px solid var(--line)", fontSize: 13, lineHeight: 1.5 }}>
            {qty != null ? (
              <>
                <span style={{ color: side === 1 ? "var(--up)" : "var(--down)", fontWeight: 600 }}>{side === 1 ? "Long" : "Short"}</span>
                {" "}≈ <span className="num">{+qty.toPrecision(4)}</span> {sel.base} at <span className="num">{usd(price!)}</span>
                {stopPct != null && (
                  <> · stop <span className="num">{usd(Number(stop))}</span> <span className={`num ${stopPct >= 0 ? "up" : "down"}`}>({stopPct >= 0 ? "+" : ""}{stopPct.toFixed(1)}%)</span></>
                )}
              </>
            ) : (
              <span className="muted">Enter a size to preview the trade.</span>
            )}
          </div>

          {err && <div className="down" style={{ fontSize: 12, marginTop: 10 }}>{err}</div>}
        </>
      )}
    </Drawer>
  );
}
