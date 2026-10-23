import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../auth";
import { deployBot, useMyBots, useMyFleets } from "../../db/queries";
import type { Visibility } from "../../db/types";
import { dol, identicon } from "../../lib/format";
import p from "../pages.module.css";
import r from "./build.module.css";
import Steps from "./Steps";
import { MissingBot, StepLoading } from "./parts";

const VIS: { key: Visibility; label: string }[] = [
  { key: "private", label: "Private" },
  { key: "results", label: "Results only" },
  { key: "public", label: "Public" },
];

export default function Deploy() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [sp] = useSearchParams();
  const startName = sp.get("bot") ?? "";
  const { data: bots, loading: botsLoading } = useMyBots(user?.id ?? null);
  const { data: fleets } = useMyFleets(user?.id ?? null);
  const bot = bots?.find((b) => b.name === startName) ?? null;

  const [name, setName] = useState(startName);
  const [fleetId, setFleetId] = useState<string | null>(null);
  const [vis, setVis] = useState<Visibility>("results");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => { if (bot) { setName(bot.name); setVis(bot.visibility); } }, [bot]);
  useEffect(() => { if (fleets && fleets.length && !fleetId) setFleetId(fleets[0].id); }, [fleets, fleetId]);

  if (botsLoading) return <StepLoading step={5} />;
  if (!bot) return <MissingBot step={5} />;

  const fleet = fleets?.find((f) => f.id === fleetId) ?? null;

  const launch = async () => {
    if (!fleetId) return;
    setErr(null);
    setBusy(true);
    const { error } = await deployBot({ bot_id: bot.id, name: name.trim() || bot.name, fleet_id: fleetId, visibility: vis });
    setBusy(false);
    if (error) { setErr(error.message); return; }
    setDone(name.trim() || bot.name);
  };

  return (
    <>
      <div className={p.crumb}>
        <span className="lk" onClick={() => nav("/build")}>Build</span> / <b>{startName}</b>
      </div>
      <Steps current={5} />
      <div className={p.body}>
        <div className={r.modalCard}>
          <div className={r.modalIcon}>
            <svg width="64" height="64" viewBox="0 0 64 64"><rect width="64" height="64" rx="16" fill="#12161D" /><path d={identicon(bot.name, 38)} fill={bot.builder?.avatar_color || "#3a81d7"} transform="translate(13 13)" /></svg>
          </div>

          {done ? (
            <>
              <h1 className={r.modalTitle}>{done} is deployed.</h1>
              <div className="lbl" style={{ textAlign: "center", marginTop: 8, lineHeight: 1.5 }}>
                It joined {fleet?.name ?? "your fleet"} and starts battling at the next check.
              </div>
              <div style={{ display: "flex", gap: 10, justifyContent: "center", marginTop: 24 }}>
                <button className={`${p.btn} ${p.pri}`} onClick={() => nav("/")}>View roster</button>
                <button className={p.btn} onClick={() => nav("/build/compose?start=describe")}>Build another</button>
              </div>
            </>
          ) : (
            <>
              <h1 className={r.modalTitle}>Deploy to a fleet</h1>

              <label className={r.field}>
                <span className={r.label}>Name</span>
                <input className={r.input} value={name} onChange={(e) => setName(e.target.value)} />
              </label>

              <div className={r.field}>
                <span className={r.label}>Fleet</span>
                <div className={p.seg} style={{ flexWrap: "wrap" }}>
                  {(fleets ?? []).map((f) => (
                    <button key={f.id} className={`${p.segBtn} ${fleetId === f.id ? p.sel : ""}`} onClick={() => setFleetId(f.id)}>
                      <span style={{ width: 8, height: 8, borderRadius: 2, background: f.color, display: "inline-block" }} />
                      {f.name}
                    </button>
                  ))}
                  {fleets && fleets.length === 0 && <span className="lbl" style={{ padding: "4px 8px" }}>No fleets yet.</span>}
                </div>
              </div>

              <div className={r.field}>
                <span className={r.label}>Visibility</span>
                <div className={p.seg}>
                  {VIS.map((o) => (
                    <button key={o.key} className={`${p.segBtn} ${vis === o.key ? p.sel : ""}`} onClick={() => setVis(o.key)}>{o.label}</button>
                  ))}
                </div>
              </div>

              <button className={`${p.btn} ${p.pri}`} style={{ height: 48, marginTop: 20, justifyContent: "center" }} disabled={busy || !fleetId} onClick={launch}>
                {busy ? "Deploying…" : `Deploy ${name.trim() || bot.name}`}
              </button>
              {err && <div style={{ color: "var(--down)", fontSize: 13, marginTop: 10, textAlign: "center" }}>{err}</div>}
              <div className="lbl" style={{ textAlign: "center", marginTop: 12 }}>
                Starts with {dol(fleet?.budget_per_bot ?? 10_000)} from the fleet's budget. The research report stays attached.
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
