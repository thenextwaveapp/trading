import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../auth";
import {
  botNameTaken,
  createFleet,
  deployBot,
  useMyBot,
  useMyFleets,
} from "../../db/queries";
import type { DbFleet, Visibility } from "../../db/types";
import { dol, identicon } from "../../lib/format";
import p from "../pages.module.css";
import r from "./build.module.css";
import Steps from "./Steps";
import { MissingBot, StepLoading } from "./parts";
import { nameIssue } from "./setup";
import { withBot } from "./stages";

const VIS: { key: Visibility; label: string }[] = [
  { key: "private", label: "Private" },
  { key: "results", label: "Results only" },
  { key: "public", label: "Public" },
];

export default function Deploy() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [sp] = useSearchParams();
  const botId = sp.get("bot") ?? "";
  const { data: bot, loading: botLoading } = useMyBot(botId || null);
  const { data: fleets } = useMyFleets(user?.id ?? null);

  const [name, setName] = useState("");
  const [fleetId, setFleetId] = useState<string | null>(null);
  const [createdFleet, setCreatedFleet] = useState<DbFleet | null>(null);
  const [vis, setVis] = useState<Visibility>("results");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    if (bot) {
      setName(bot.name);
      setVis(bot.visibility);
    }
  }, [bot]);

  const allFleets = useMemo(
    () => (createdFleet ? [...(fleets ?? []), createdFleet] : fleets ?? []),
    [fleets, createdFleet],
  );
  useEffect(() => {
    if (allFleets.length && !fleetId) setFleetId(allFleets[0].id);
  }, [allFleets, fleetId]);

  if (botLoading) return <StepLoading step={5} />;
  if (!bot) return <MissingBot step={5} />;

  const fleet = allFleets.find((f) => f.id === fleetId) ?? null;
  const spec = bot.spec as Record<string, unknown> | null;
  const partial = !spec || spec.partial === true;
  const deployed = bot.stage === "deployed";
  const blocked = !deployed && (bot.stage !== "ready" || partial);

  const makeFleet = async (): Promise<string | null> => {
    if (!user) {
      setErr("Sign in again to create a fleet.");
      return null;
    }
    const { data, error } = await createFleet(user.id);
    if (error || !data) {
      setErr(error?.message ?? "Could not create a fleet.");
      return null;
    }
    setCreatedFleet(data as DbFleet);
    setFleetId(data.id);
    return data.id;
  };

  const launch = async () => {
    const finalName = name.trim();
    const bad = nameIssue(finalName);
    if (bad) { setErr(bad); return; }

    setErr(null);
    setBusy(true);
    if (user) {
      const taken = await botNameTaken(user.id, finalName, bot.id);
      if (taken.error) { setBusy(false); setErr(taken.error.message); return; }
      if (taken.taken) {
        setBusy(false);
        setErr("You already have a bot with that name. Pick another.");
        return;
      }
    }

    let target = fleetId;
    if (!target) target = await makeFleet();
    if (!target) { setBusy(false); return; }

    const { data, error } = await deployBot({
      bot_id: bot.id,
      name: finalName,
      fleet_id: target,
      visibility: vis,
    });
    setBusy(false);
    if (error || !data) {
      setErr(error?.message ?? "Could not deploy the bot.");
      return;
    }
    setDone(data.name);
  };

  return (
    <>
      <div className={p.crumb}>
        <span className="lk" onClick={() => nav("/build")}>Build</span> / <b>{bot.name}</b>
      </div>
      <Steps current={5} />
      <div className={p.body}>
        <div className={r.modalCard}>
          <div className={r.modalIcon}>
            <svg width="64" height="64" viewBox="0 0 64 64"><rect width="64" height="64" rx="16" fill="#12161D" /><path d={identicon(name || bot.name, 38)} fill={bot.builder?.avatar_color || "#3a81d7"} transform="translate(13 13)" /></svg>
          </div>

          {done ? (
            <>
              <h1 className={r.modalTitle}>{done} is deployed.</h1>
              <div className="lbl" style={{ textAlign: "center", marginTop: 8, lineHeight: 1.5 }}>
                It joined {fleet?.name ?? "your fleet"} and starts battling at the next check.
              </div>
              <div style={{ display: "flex", gap: 10, justifyContent: "center", marginTop: 24 }}>
                <button className={`${p.btn} ${p.pri}`} onClick={() => nav("/bot/" + encodeURIComponent(done))}>View bot</button>
                <button className={p.btn} onClick={() => nav("/build/compose")}>Build another</button>
              </div>
            </>
          ) : blocked ? (
            <>
              <h1 className={r.modalTitle}>
                {bot.stage === "deployed" ? "Already deployed." : partial ? "No deployable spec yet." : "Not certified yet."}
              </h1>
              <div className="lbl" style={{ textAlign: "center", marginTop: 8, lineHeight: 1.6 }}>
                {partial
                  ? "The engine hasn't written a complete spec for this bot. Finish training so the worker can persist the full rules, then close Weather."
                  : `This bot is in ${bot.stage}. Close Weather to certify it before deploying.`}
              </div>
              <div style={{ display: "flex", gap: 10, justifyContent: "center", marginTop: 24, flexWrap: "wrap" }}>
                {partial ? (
                  <button className={`${p.btn} ${p.pri}`} onClick={() => nav(withBot("/build/training", bot.id))}>Go to training</button>
                ) : (
                  <button className={`${p.btn} ${p.pri}`} onClick={() => nav(withBot("/build/weather", bot.id))}>Go to weather</button>
                )}
                <button className={p.btn} onClick={() => nav("/build")}>Back to Build</button>
              </div>
            </>
          ) : deployed ? (
            <>
              <h1 className={r.modalTitle}>{bot.name} is already deployed.</h1>
              <div className="lbl" style={{ textAlign: "center", marginTop: 8, lineHeight: 1.5 }}>
                It's already in {fleet?.name ?? "a fleet"} — deploy isn't run twice.
              </div>
              <div style={{ display: "flex", gap: 10, justifyContent: "center", marginTop: 24 }}>
                <button className={`${p.btn} ${p.pri}`} onClick={() => nav("/bot/" + encodeURIComponent(bot.name))}>View bot</button>
                <button className={p.btn} onClick={() => nav("/build")}>Back to Build</button>
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
                  {allFleets.map((f) => (
                    <button key={f.id} className={`${p.segBtn} ${fleetId === f.id ? p.sel : ""}`} onClick={() => setFleetId(f.id)}>
                      <span style={{ width: 8, height: 8, borderRadius: 2, background: f.color, display: "inline-block" }} />
                      {f.name}
                    </button>
                  ))}
                  {allFleets.length === 0 && (
                    <button className={p.segBtn} onClick={() => void makeFleet()}>
                      + Create My Fleet
                    </button>
                  )}
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

              <button className={`${p.btn} ${p.pri}`} style={{ height: 48, marginTop: 20, justifyContent: "center" }} disabled={busy} onClick={launch}>
                {busy ? "Deploying…" : `Deploy ${name.trim() || bot.name}`}
              </button>
              {err && <div style={{ color: "var(--down)", fontSize: 13, marginTop: 10, textAlign: "center" }}>{err}</div>}
              <div className="lbl" style={{ textAlign: "center", marginTop: 12 }}>
                Starts with {dol(fleet?.budget_per_bot ?? 10_000)} from the fleet's budget. The backtest, trials and weather gate stay attached.
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
