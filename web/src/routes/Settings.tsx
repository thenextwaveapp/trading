import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useData } from "../api/context";
import { useAssistant } from "../assistant/AssistantProvider";
import { useAuth } from "../auth";
import { updateBuilderProfile, uploadAvatar } from "../db/queries";
import { DEFAULT_BOT_COLOR, FLEET_PALETTE } from "../lib/brand";
import { ago, clock, identicon, TZ } from "../lib/format";
import p from "./pages.module.css";

const TABS = ["Profile", "Sharing", "Defaults", "Alerts", "Plan", "System"];

export default function Settings() {
  const d = useData();
  const nav = useNavigate();
  const { profile, user, refreshProfile, signOut } = useAuth();
  const assistant = useAssistant();
  const [tab, setTab] = useState("Sharing");

  const [displayName, setDisplayName] = useState("");
  const [bio, setBio] = useState("");
  const [avatarColor, setAvatarColor] = useState(DEFAULT_BOT_COLOR);
  const [profilePublic, setProfilePublic] = useState(true);
  const [botsOnBoard, setBotsOnBoard] = useState(true);
  const [seeded, setSeeded] = useState(false);
  const [uploading, setUploading] = useState(false);

  const onPickAvatar = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !user) return;
    setUploading(true);
    const { error } = await uploadAvatar(user.id, file);
    if (!error) await refreshProfile();
    setUploading(false);
    e.target.value = "";
  };

  useEffect(() => {
    if (profile && !seeded) {
      setDisplayName(profile.display_name ?? "");
      setBio(profile.bio ?? "");
      setAvatarColor(profile.avatar_color || DEFAULT_BOT_COLOR);
      setProfilePublic(profile.profile_public ?? true);
      setBotsOnBoard(profile.bots_on_leaderboard ?? true);
      setSeeded(true);
    }
  }, [profile, seeded]);

  useEffect(() => {
    if (!seeded || !user) return;
    const t = setTimeout(async () => {
      await updateBuilderProfile(user.id, {
        display_name: displayName.trim() || null,
        bio: bio.trim() || null,
        avatar_color: avatarColor,
        profile_public: profilePublic,
        bots_on_leaderboard: botsOnBoard,
      });
      await refreshProfile();
    }, 450);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [displayName, bio, avatarColor, profilePublic, botsOnBoard, seeded, user]);

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
          user ? (
            <div style={{ maxWidth: 560, display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                {profile?.avatar_url ? (
                  <img
                    src={profile.avatar_url}
                    alt=""
                    width={64}
                    height={64}
                    style={{ flex: "none", borderRadius: "50%", objectFit: "cover", background: "#12161D" }}
                  />
                ) : (
                  <svg width="64" height="64" viewBox="0 0 64 64" style={{ flex: "none" }}>
                    <rect width="64" height="64" rx="32" fill="#12161D" />
                    <path d={identicon("@" + (profile?.handle ?? "builder"), 38)} fill={avatarColor} transform="translate(13 13)" />
                  </svg>
                )}
                <div>
                  <div style={{ fontSize: 18, fontWeight: 500 }}>@{profile?.handle ?? "…"}</div>
                  <div className="lbl" style={{ marginTop: 4 }}>{user.email ?? "—"}</div>
                  <label className={`${p.btn} ${p.sm}`} style={{ marginTop: 8, cursor: "pointer" }}>
                    {uploading ? "Uploading…" : profile?.avatar_url ? "Change photo" : "Upload photo"}
                    <input type="file" accept="image/*" hidden disabled={uploading} onChange={onPickAvatar} />
                  </label>
                </div>
              </div>
              <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span className="lbl">Display name</span>
                <input
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Your display name"
                  style={{ height: 44, padding: "0 14px", borderRadius: 10, border: "1px solid var(--border)", background: "#0d1117", color: "var(--fg)", font: "inherit", fontSize: 14 }}
                />
              </label>
              <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span className="lbl">Bio</span>
                <input
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                  placeholder="Short bio on your builder profile"
                  style={{ height: 44, padding: "0 14px", borderRadius: 10, border: "1px solid var(--border)", background: "#0d1117", color: "var(--fg)", font: "inherit", fontSize: 14 }}
                />
              </label>
              <div>
                <div className="lbl" style={{ marginBottom: 8 }}>Avatar color</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {FLEET_PALETTE.flatMap((h) => h.shades).map((c) => (
                    <button
                      key={c}
                      type="button"
                      onClick={() => setAvatarColor(c)}
                      style={{
                        width: 22,
                        height: 22,
                        borderRadius: "50%",
                        background: c,
                        border: avatarColor === c ? "2px solid var(--fg)" : "2px solid transparent",
                        cursor: "pointer",
                      }}
                    />
                  ))}
                </div>
              </div>
              <div style={{ display: "flex", gap: 10, marginTop: 6 }}>
                {profile?.handle && (
                  <button className={`${p.btn} ${p.sm}`} onClick={() => nav("/builder/" + encodeURIComponent(profile.handle))}>
                    View builder profile
                  </button>
                )}
                <button className={`${p.btn} ${p.sm}`} onClick={() => signOut()}>Log out</button>
              </div>
            </div>
          ) : (
            <div style={{ maxWidth: 560, display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="lbl">You're not logged in. Log in to see your profile, build strategies, and run your own fleet.</div>
              <button className={`${p.btn} ${p.sm}`} style={{ width: "fit-content" }} onClick={() => nav("/signin")}>Log in</button>
            </div>
          )
        )}

        {tab === "Sharing" && (
          <div style={{ maxWidth: 580, display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="card" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 18 }}>
              <div>
                <div style={{ fontSize: 16, fontWeight: 500 }}>Builder privacy</div>
                <div className="lbl" style={{ marginTop: 4, lineHeight: 1.5 }}>
                  Control whether your builder profile and deployed bots appear in public search and on the Leaderboard.
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, paddingTop: 12, borderTop: "1px solid var(--line)" }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 500 }}>Public builder profile</div>
                  <div className="lbl" style={{ marginTop: 3 }}>
                    Allow others to find @{profile?.handle ?? "you"} in search and view your builder page.
                  </div>
                </div>
                <div className={p.seg}>
                  <button className={`${p.segBtn} ${profilePublic ? p.sel : ""}`} onClick={() => setProfilePublic(true)}>Public</button>
                  <button className={`${p.segBtn} ${!profilePublic ? p.sel : ""}`} onClick={() => setProfilePublic(false)}>Private</button>
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, paddingTop: 12, borderTop: "1px solid var(--line)" }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 500 }}>Show bots on Leaderboard</div>
                  <div className="lbl" style={{ marginTop: 3 }}>
                    Include your non-private deployed bots on the public Leaderboard.
                  </div>
                </div>
                <div className={p.seg}>
                  <button className={`${p.segBtn} ${botsOnBoard ? p.sel : ""}`} onClick={() => setBotsOnBoard(true)}>Shown</button>
                  <button className={`${p.segBtn} ${!botsOnBoard ? p.sel : ""}`} onClick={() => setBotsOnBoard(false)}>Hidden</button>
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, paddingTop: 12, borderTop: "1px solid var(--line)" }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 500 }}>Assistant</div>
                  <div className="lbl" style={{ marginTop: 3 }}>
                    The chart-aware helper in the corner that answers questions and drafts bots.
                  </div>
                </div>
                <div className={p.seg}>
                  <button className={`${p.segBtn} ${assistant.enabled ? p.sel : ""}`} onClick={() => assistant.setEnabled(true)}>On</button>
                  <button className={`${p.segBtn} ${!assistant.enabled ? p.sel : ""}`} onClick={() => assistant.setEnabled(false)}>Off</button>
                </div>
              </div>
            </div>
          </div>
        )}

        {tab === "Defaults" && (
          <div style={{ maxWidth: 560, display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="card" style={{ padding: 20 }}>
              <div style={{ fontSize: 15, fontWeight: 500 }}>Bot defaults</div>
              <div className="lbl" style={{ marginTop: 6, lineHeight: 1.5 }}>Starting capital, concurrency and drawdown thresholds for new bots.</div>
              <Field label="Starting capital" value="$10,000" />
              <Field label="Max concurrent" value="6" />
              <Field label="Drawdown threshold" value="-5%" />
            </div>
          </div>
        )}

        {tab === "Plan" && (
          <div style={{ maxWidth: 560, display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="card" style={{ padding: 20 }}>
              <div style={{ fontSize: 15, fontWeight: 500 }}>Your plan</div>
              <div className="lbl" style={{ marginTop: 6, lineHeight: 1.5 }}>Paper Fleet is free to start. Upgrade for live capital and higher limits.</div>
              <Field label="Plan" value="Free" />
              <Field label="Fleets" value="1" />
              <Field label="Bots" value="Unlimited (paper)" />
            </div>
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
