import { useState } from "react";
import { useData } from "../api/context";
import { useProfile } from "../db/queries";
import { CURRENT_HANDLE } from "../session";
import { ago, clock, TZ } from "../lib/format";
import p from "./pages.module.css";

const TABS = ["Profile", "System", "Alerts"];

export default function Settings() {
  const d = useData();
  const { data: profile } = useProfile(CURRENT_HANDLE);
  const [tab, setTab] = useState("System");

  const liveOk = d.running && !d.paused;
  const errs = d.log.filter((l) => /error|exception|traceback/i.test(l)).length;

  return (
    <>
      <div className={p.top}>
        <div>
          <h1 className={p.title}>Settings</h1>
          <div className={p.subtitle}>Your profile, alerts and the services that run your bots.</div>
        </div>
      </div>
      <div className={p.body}>
        <div className={p.seg} style={{ marginBottom: 24, width: "fit-content" }}>
          {TABS.map((t) => (
            <button key={t} className={`${p.segBtn} ${tab === t ? p.sel : ""}`} onClick={() => setTab(t)}>{t}</button>
          ))}
        </div>

        {tab === "Profile" && (
          <div style={{ maxWidth: 560, display: "flex", flexDirection: "column", gap: 16 }}>
            <Field label="Handle" value={"@" + (profile?.handle ?? "…")} />
            <Field label="Display name" value={profile?.display_name ?? "—"} />
            <div>
              <div className="lbl" style={{ marginBottom: 6 }}>Avatar color</div>
              <span style={{ display: "inline-block", width: 30, height: 30, borderRadius: 8, background: profile?.avatar_color ?? "#3a81d7" }} />
            </div>
            <div className="lbl">Profiles live in the database. Editing arrives with sign-in &amp; the write backend.</div>
          </div>
        )}

        {tab === "System" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 12 }}>
              <StatusCard title="Trading engine" ok={!!liveOk} status={liveOk ? "Running" : d.paused ? "Paused" : "Down"}
                rows={[["State", d.loaded ? "loaded" : "not loaded"], ["Updated", ago(d.state_age_s)], ["Errors in log", String(errs)]]} />
              <StatusCard title="Market data" ok={d.state_age_s != null && d.state_age_s < 1800} status={d.state_age_s != null && d.state_age_s < 1800 ? "Healthy" : "Stale"}
                rows={[["Coins", String(Object.keys(d.symbols).length)], ["BTC 4h", d.gate.bear == null ? "—" : d.gate.bear ? "bear" : "bull"], ["Last mark", ago(d.state_age_s)]]} />
              <StatusCard title="Data source" ok={d._source !== "local-stale"} status={d._source === "upstream" ? "Live" : d._source === "local-stale" ? "Stale copy" : "Local"}
                rows={[["Feed", d._source ?? "direct"], ["Timezone", TZ]]} />
            </div>
            <div>
              <h2 className={p.h2} style={{ marginBottom: 12 }}>Recent activity</h2>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, lineHeight: 1.75, color: "var(--muted)", background: "var(--card-bottom)", border: "1px solid var(--line-2)", borderRadius: 12, padding: "14px 16px", maxHeight: 280, overflow: "auto", whiteSpace: "pre-wrap" }}>
                {d.log.length ? d.log.slice(-20).join("\n") : "(no recent log lines)"}
              </div>
            </div>
          </div>
        )}

        {tab === "Alerts" && (
          <div style={{ maxWidth: 560, display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="card" style={{ padding: 20 }}>
              <div style={{ fontSize: 15, fontWeight: 500 }}>Phone notifications (ntfy)</div>
              <div className="lbl" style={{ marginTop: 6, lineHeight: 1.5 }}>Install the free ntfy app, subscribe to your topic, and the fleet pushes entries, exits, kill-switch trips and errors.</div>
              <Field label="Your topic" value={d.ntfy || "off"} mono />
              <div className="lbl" style={{ marginTop: 8 }}>Anyone with the topic can read your alerts — keep it private. Set it on the ops dashboard.</div>
            </div>
            <div className="lbl">Last check: {d.log.length ? clock(d.now) : "—"} · times in {TZ}</div>
          </div>
        )}
      </div>
    </>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="lbl" style={{ marginBottom: 6 }}>{label}</div>
      <div className={mono ? "num" : ""} style={{ height: 46, display: "flex", alignItems: "center", padding: "0 14px", borderRadius: 10, border: "1px solid var(--border)", background: "#0d1117", color: "var(--fg)", fontSize: 14 }}>{value}</div>
    </div>
  );
}
function StatusCard({ title, ok, status, rows }: { title: string; ok: boolean; status: string; rows: [string, string][] }) {
  return (
    <div className="card" style={{ padding: 18 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 14, fontWeight: 500 }}>{title}</span>
        <span className="chip"><span className={ok ? "liveDot" : "downDot"} />{status}</span>
      </div>
      <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
        {rows.map(([k, v]) => (
          <div key={k} style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
            <span className="muted">{k}</span><span className="num">{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
