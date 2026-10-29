import { useState } from "react";
import type { Position } from "../api/types";
import { queuePositionAction } from "../db/queries";
import { pct, usd } from "../lib/format";
import Drawer from "./Drawer";

const inputStyle: React.CSSProperties = {
  height: 42, width: "100%", padding: "0 12px", borderRadius: "var(--radius-sm)",
  border: "1px solid var(--border)", background: "#0d1117", color: "var(--fg)",
  font: "inherit", fontSize: 14,
};

function num(v: number | null | undefined, max = 8): string {
  return v == null ? "" : String(+v.toFixed(max));
}

export default function ManagePosition({
  botId, botName, pos, onClose, onClosed,
}: {
  botId: string; botName: string; pos: Position; onClose: () => void; onClosed?: () => void;
}) {
  const [stop, setStop] = useState(num(pos.stop));
  const [tp, setTp] = useState(num(pos.tp));
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);

  const up = (pos.upnl ?? 0) >= 0;

  const updateExits = async () => {
    setBusy(true);
    if (stop !== "" && Number(stop) !== pos.stop)
      await queuePositionAction({ bot_id: botId, ticker: pos.ticker, action: "set_stop", value: Number(stop) });
    if (tp !== "" && Number(tp) !== (pos.tp ?? 0))
      await queuePositionAction({ bot_id: botId, ticker: pos.ticker, action: "set_tp", value: Number(tp) });
    setBusy(false);
    setSaved(true);
  };

  const closePosition = async () => {
    setBusy(true);
    await queuePositionAction({ bot_id: botId, ticker: pos.ticker, action: "close" });
    onClosed?.();   // optimistically remove from the table
    onClose();      // dismiss the drawer — the engine closes it within seconds
  };

  const row = (label: string, value: string, cls = "") => (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "9px 0", borderTop: "1px solid var(--line)" }}>
      <span className="lbl">{label}</span>
      <span className={`num ${cls}`}>{value}</span>
    </div>
  );

  const footer = confirmClose ? (
    <div style={{ display: "flex", gap: 8 }}>
      <button className="btn" style={{ flex: 1 }} disabled={busy} onClick={() => setConfirmClose(false)}>Cancel</button>
      <button className="btn" style={{ flex: 1, borderColor: "var(--down)", color: "var(--down)" }} disabled={busy} onClick={() => void closePosition()}>
        {busy ? "…" : "Confirm close"}
      </button>
    </div>
  ) : (
    <button className="btn" style={{ width: "100%", borderColor: "color-mix(in srgb, var(--down) 45%, transparent)", color: "var(--down)" }} onClick={() => setConfirmClose(true)}>
      Close position
    </button>
  );

  return (
    <Drawer title="Manage position" onClose={onClose} footer={footer}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
        <span style={{ fontSize: 22, fontWeight: 600 }}>{pos.ticker}</span>
        <span style={{
          fontSize: 11, fontWeight: 600, padding: "2px 7px", borderRadius: 4,
          color: pos.side === "short" ? "var(--down)" : "var(--up)",
          background: `color-mix(in srgb, ${pos.side === "short" ? "var(--down)" : "var(--up)"} 15%, transparent)`,
        }}>{pos.side.toUpperCase()}</span>
        <span className="lbl" style={{ marginLeft: "auto" }}>{botName}</span>
      </div>

      <div style={{ margin: "10px 0 20px" }}>
        {row("Unrealized P&L", usd(pos.upnl ?? 0, true), up ? "up" : "down")}
        {row("Return", pct(pos.upct != null ? pos.upct * 100 : null, true), up ? "up" : "down")}
        {row("Entry", usd(pos.entry))}
        {row("Current", pos.px != null ? usd(pos.px) : "—")}
        {row("Size", usd(pos.notional))}
      </div>

      <label style={{ display: "block", marginBottom: 14 }}>
        <span className="lbl" style={{ display: "block", marginBottom: 6 }}>Stop loss (price)</span>
        <input style={inputStyle} inputMode="decimal" value={stop} onChange={(e) => { setStop(e.target.value); setSaved(false); }} placeholder="No stop" />
      </label>
      <label style={{ display: "block", marginBottom: 16 }}>
        <span className="lbl" style={{ display: "block", marginBottom: 6 }}>Take profit (price)</span>
        <input style={inputStyle} inputMode="decimal" value={tp} onChange={(e) => { setTp(e.target.value); setSaved(false); }} placeholder="No take profit" />
      </label>

      <button className={`btn pri`} style={{ width: "100%", height: 40, justifyContent: "center" }} disabled={busy} onClick={() => void updateExits()}>
        {busy ? "Saving…" : saved ? "Exits updated ✓" : "Update exits"}
      </button>
      {saved && <div className="muted" style={{ fontSize: 12, marginTop: 8, textAlign: "center" }}>Queued — the engine applies it next cycle.</div>}
    </Drawer>
  );
}
