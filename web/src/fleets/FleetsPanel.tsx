import { useEffect, useRef, useState } from "react";
import { useAuth } from "../auth";
import { createFleet, deleteFleet, updateFleet } from "../db/queries";
import type { DbFleet } from "../db/types";
import { FLEET_SLOTS } from "../lib/brand";
import { entitlementOf, FREE_MAX_FLEETS } from "../lib/billing";
import { useUpgrade } from "../components/UpgradeModal";
import Segmented from "../components/Segmented";
import p from "../routes/pages.module.css";
import { useCurrentFleet } from "./CurrentFleetProvider";

const MARKETS = [
  { key: "crypto", label: "Crypto" },
  { key: "fx_spot", label: "Forex" },
  { key: "equity", label: "Stocks" },
];

const inputStyle: React.CSSProperties = {
  height: 44,
  padding: "0 14px",
  borderRadius: 10,
  border: "1px solid var(--border)",
  background: "#0d1117",
  color: "var(--fg)",
  font: "inherit",
  fontSize: 14,
  width: "100%",
};

export default function FleetsPanel() {
  const { fleets, currentId, setCurrentId, upsertFleet, removeFleet } = useCurrentFleet();
  const { user, subscription } = useAuth();
  const upgrade = useUpgrade();
  const [creating, setCreating] = useState(false);

  const addFleet = async () => {
    if (!user || creating) return;
    if (!entitlementOf(subscription).entitled && fleets.length >= FREE_MAX_FLEETS) {
      upgrade.open("Multiple fleets are a Pro feature.");
      return;
    }
    setCreating(true);
    const { data } = await createFleet(user.id, `Fleet ${fleets.length + 1}`);
    setCreating(false);
    if (!data) return;
    upsertFleet(data as DbFleet);
    setCurrentId((data as DbFleet).id);
  };

  return (
    <div style={{ width: "100%", maxWidth: 620, display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 16 }}>
        <div className="lbl" style={{ lineHeight: 1.5 }}>
          A fleet is a book your deployed bots trade in — its own budget, cadence and kill-switch.
          Switch the active fleet from the picker on the Fleet page.
        </div>
        <button className={`${p.btn} ${p.sm}`} style={{ flex: "none" }} disabled={creating} onClick={addFleet}>
          {creating ? "Creating…" : "＋ New fleet"}
        </button>
      </div>

      {fleets.map((f) => (
        <FleetCard
          key={f.id}
          fleet={f}
          isCurrent={f.id === currentId}
          canDelete={fleets.length > 1}
          onCurrent={() => setCurrentId(f.id)}
          onSaved={upsertFleet}
          onDeleted={() => removeFleet(f.id)}
        />
      ))}
    </div>
  );
}

function FleetCard({
  fleet,
  isCurrent,
  canDelete,
  onCurrent,
  onSaved,
  onDeleted,
}: {
  fleet: DbFleet;
  isCurrent: boolean;
  canDelete: boolean;
  onCurrent: () => void;
  onSaved: (f: DbFleet) => void;
  onDeleted: () => void;
}) {
  const [name, setName] = useState(fleet.name);
  const [color, setColor] = useState(fleet.color);
  const [market, setMarket] = useState(fleet.market);
  const [status, setStatus] = useState(fleet.status);
  const [budget, setBudget] = useState(String(fleet.budget_per_bot));
  const [interval, setIntervalMin] = useState(String(fleet.check_interval_min));
  const [kill, setKill] = useState(fleet.kill_switch_pct == null ? "" : String(fleet.kill_switch_pct));
  const [bench, setBench] = useState(fleet.benchmark_pct == null ? "" : String(fleet.benchmark_pct));
  const [description, setDescription] = useState(fleet.description ?? "");
  const [confirmDel, setConfirmDel] = useState(false);
  const firstRun = useRef(true);

  // Debounced autosave, mirroring the Profile tab's pattern. Skip the initial
  // run so merely opening the tab doesn't rewrite every fleet.
  useEffect(() => {
    if (firstRun.current) {
      firstRun.current = false;
      return;
    }
    const t = setTimeout(async () => {
      const num = (v: string) => (v.trim() === "" ? null : Number(v));
      const { data } = await updateFleet(fleet.id, {
        name: name.trim() || "Fleet",
        color,
        market,
        status,
        budget_per_bot: Number(budget) || 0,
        check_interval_min: Math.max(1, Math.round(Number(interval) || 15)),
        kill_switch_pct: num(kill),
        benchmark_pct: num(bench),
        description: description.trim() || null,
      });
      if (data) onSaved(data as DbFleet);
    }, 500);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, color, market, status, budget, interval, kill, bench, description]);

  const del = async () => {
    await deleteFleet(fleet.id);
    onDeleted();
  };

  return (
    <div className="card" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{ width: 12, height: 12, borderRadius: "50%", background: color, flex: "none" }} />
        <input value={name} onChange={(e) => setName(e.target.value)} style={{ ...inputStyle, fontWeight: 500 }} placeholder="Fleet name" />
        {isCurrent ? (
          <span className="chip" style={{ flex: "none" }}>Current</span>
        ) : (
          <button className={`${p.btn} ${p.sm}`} style={{ flex: "none" }} onClick={onCurrent}>Set current</button>
        )}
      </div>

      <div>
        <div className="lbl" style={{ marginBottom: 8 }}>Color</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {FLEET_SLOTS.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setColor(c)}
              style={{
                width: 24,
                height: 24,
                borderRadius: "50%",
                background: c,
                border: color === c ? "2px solid var(--fg)" : "2px solid transparent",
                cursor: "pointer",
              }}
            />
          ))}
        </div>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="lbl">Market</span>
          <Segmented
            ariaLabel="Fleet market"
            value={market}
            onChange={setMarket}
            options={MARKETS.map((m) => ({ value: m.key, label: m.label }))}
          />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="lbl">Status</span>
          <Segmented
            ariaLabel="Fleet status"
            value={status}
            onChange={setStatus}
            options={[
              { value: "active", label: "Active" },
              { value: "paused", label: "Paused" },
            ]}
          />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 14 }}>
        <Num label="Budget / bot ($)" value={budget} onChange={setBudget} step="1000" />
        <Num label="Check every (min)" value={interval} onChange={setIntervalMin} step="1" />
        <Num label="Kill switch (%)" value={kill} onChange={setKill} step="1" placeholder="off" />
        <Num label="Benchmark (%)" value={bench} onChange={setBench} step="0.5" placeholder="none" />
      </div>

      <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span className="lbl">Description</span>
        <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What this fleet is for" style={inputStyle} />
      </label>

      <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: 4, borderTop: "1px solid var(--line)" }}>
        {confirmDel ? (
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="lbl">Delete “{fleet.name}”? Its bots keep running, unassigned.</span>
            <button className={`${p.btn} ${p.sm}`} onClick={() => setConfirmDel(false)}>Cancel</button>
            <button className={`${p.btn} ${p.sm}`} style={{ color: "var(--down)" }} onClick={del}>Delete</button>
          </div>
        ) : (
          <button
            className={`${p.btn} ${p.sm}`}
            disabled={!canDelete}
            title={canDelete ? "Delete fleet" : "You need at least one fleet"}
            onClick={() => setConfirmDel(true)}
          >
            Delete fleet
          </button>
        )}
      </div>
    </div>
  );
}

function Num({
  label,
  value,
  onChange,
  step,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  step?: string;
  placeholder?: string;
}) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <span className="lbl">{label}</span>
      <input
        type="number"
        step={step}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        style={{ ...inputStyle, height: 42 }}
      />
    </label>
  );
}
