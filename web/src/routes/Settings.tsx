import { useEffect, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useData } from "../api/context";
import { useAssistant } from "../assistant/AssistantProvider";
import { useAuth } from "../auth";
import { useCurrentFleet } from "../fleets/CurrentFleetProvider";
import FleetsPanel from "../fleets/FleetsPanel";
import Segmented from "../components/Segmented";
import { UserAvatar } from "../components/Avatar";
import AvatarCropper from "../components/AvatarCropper";
import { updateBuilderProfile, uploadAvatar } from "../db/queries";
import { DEFAULT_BOT_COLOR } from "../lib/brand";
import { ago, clock, TZ } from "../lib/format";
import {
  entitlementOf, startCheckout, openBillingPortal,
  PRICE_LABEL, PRICE_PERIOD, TRIAL_DAYS,
} from "../lib/billing";
import p from "./pages.module.css";
import { builderPath } from "../lib/paths";

const TABS = ["Builder", "Defaults", "Fleets", "Alerts", "Plan", "System"];

// Two standard widths: the Fleets cards are the wide tier (620, set in
// FleetsPanel); the filter bar and every other tab's cards share this narrower
// tier so the page reads as two tidy column widths, not five random ones.
const FORM_W = 520;

export default function Settings() {
  const d = useData();
  const nav = useNavigate();
  const loc = useLocation();
  const { profile, user, refreshProfile, signOut } = useAuth();
  const assistant = useAssistant();
  const { fleets } = useCurrentFleet();
  const [sp] = useSearchParams();
  const [tab, setTab] = useState(() => {
    // Tab can come from router state (in-app nav) or a ?tab= query (e.g. the
    // return from Stripe checkout, which is a full page load with no state).
    let want = (loc.state as { tab?: string } | null)?.tab ?? sp.get("tab") ?? undefined;
    // Profile + Sharing merged into one "Builder" tab — honor old deep links.
    if (want === "Profile" || want === "Sharing") want = "Builder";
    return want && TABS.includes(want) ? want : "Builder";
  });

  const [displayName, setDisplayName] = useState("");
  const [bio, setBio] = useState("");
  const [avatarColor, setAvatarColor] = useState(DEFAULT_BOT_COLOR);
  const [profilePublic, setProfilePublic] = useState(true);
  const [botsOnBoard, setBotsOnBoard] = useState(true);
  const [shareToFeed, setShareToFeed] = useState(true);
  const [seeded, setSeeded] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [cropFile, setCropFile] = useState<File | null>(null);

  // Picking a file opens the cropper (no immediate upload); the cropper hands
  // back a square PNG, which is what we actually store.
  const onPickAvatar = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) setCropFile(file);
  };

  const onCropped = async (cropped: File) => {
    if (!user) return;
    setUploading(true);
    const { error } = await uploadAvatar(user.id, cropped);
    if (!error) await refreshProfile();
    setUploading(false);
    setCropFile(null);
  };

  useEffect(() => {
    if (profile && !seeded) {
      setDisplayName(profile.display_name ?? "");
      setBio(profile.bio ?? "");
      setAvatarColor(profile.avatar_color || DEFAULT_BOT_COLOR);
      setProfilePublic(profile.profile_public ?? true);
      setBotsOnBoard(profile.bots_on_leaderboard ?? true);
      setShareToFeed(profile.share_to_feed ?? true);
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
        share_to_feed: shareToFeed,
      });
      await refreshProfile();
    }, 450);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [displayName, bio, avatarColor, profilePublic, botsOnBoard, shareToFeed, seeded, user]);

  const liveOk = d.running && !d.paused;
  const errs = d.log.filter((l) => /error|exception|traceback/i.test(l)).length;

  return (
    <>
      <div className={`${p.shell} ${p.body}`} style={{ paddingTop: 36, display: "flex", flexDirection: "column", alignItems: "center" }}>
        <div style={{ marginBottom: 24, width: "100%", maxWidth: FORM_W }}>
          <Segmented
            ariaLabel="Settings section"
            value={tab}
            onChange={setTab}
            block
            options={TABS.map((t) => ({ value: t, label: t }))}
          />
        </div>

        {tab === "Builder" && (
          user ? (
            <div style={{ width: "100%", maxWidth: FORM_W, display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                <label
                  title={uploading ? "Uploading…" : "Change photo"}
                  style={{ position: "relative", flex: "none", lineHeight: 0, cursor: uploading ? "default" : "pointer", opacity: uploading ? 0.6 : 1 }}
                >
                  <UserAvatar
                    name={displayName || profile?.display_name}
                    handle={profile?.handle}
                    url={profile?.avatar_url}
                    color={avatarColor}
                    size={64}
                  />
                  <span
                    aria-hidden
                    style={{
                      position: "absolute", right: -2, bottom: -2, width: 24, height: 24,
                      borderRadius: "50%", background: "var(--accent)", color: "#fff",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      border: "2px solid #0d1117",
                    }}
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h3l2-3h8l2 3h3a2 2 0 0 1 2 2z" />
                      <circle cx="12" cy="13" r="4" />
                    </svg>
                  </span>
                  <input type="file" accept="image/*" hidden disabled={uploading} onChange={onPickAvatar} />
                </label>
                <div>
                  <div style={{ fontSize: 18, fontWeight: 500 }}>@{profile?.handle ?? "…"}</div>
                  <div className="lbl" style={{ marginTop: 4 }}>{user.email ?? "—"}</div>
                  <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                    {profile?.handle && (
                      <button className={`${p.btn} ${p.sm}`} onClick={() => nav(builderPath(profile.handle))}>
                        View builder profile
                      </button>
                    )}
                    <button className={`${p.btn} ${p.sm}`} style={{ color: "var(--muted)" }} onClick={() => signOut()}>Log out</button>
                  </div>
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
            </div>
          ) : (
            <div style={{ width: "100%", maxWidth: FORM_W, display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="lbl">You're not logged in.</div>
              <button className={`${p.btn} ${p.sm}`} style={{ width: "fit-content" }} onClick={() => nav("/signin")}>Log in</button>
            </div>
          )
        )}

        {tab === "Builder" && user && (
          <div style={{ width: "100%", maxWidth: FORM_W, display: "flex", flexDirection: "column", gap: 16, marginTop: 28 }}>
            <div className="card" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 18 }}>
              <div>
                <div style={{ fontSize: 16, fontWeight: 500 }}>Builder privacy</div>
                <div className="lbl" style={{ marginTop: 4, lineHeight: 1.5 }}>
                  Account-wide switches for what you share publicly — your builder profile, the Leaderboard, and the activity feed. Each bot's own visibility (Private / Results / Public, set when you deploy) is the finer dial, and also decides who can copy it.
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, paddingTop: 12, borderTop: "1px solid var(--line)" }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 500 }}>Public builder profile</div>
                  <div className="lbl" style={{ marginTop: 3 }}>
                    Allow others to find @{profile?.handle ?? "you"} in search and view your builder page.
                  </div>
                </div>
                <Segmented
                  ariaLabel="Profile visibility"
                  value={profilePublic ? "public" : "private"}
                  onChange={(v) => setProfilePublic(v === "public")}
                  options={[
                    { value: "public", label: "Public" },
                    { value: "private", label: "Private" },
                  ]}
                />
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, paddingTop: 12, borderTop: "1px solid var(--line)" }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 500 }}>Show bots on Leaderboard</div>
                  <div className="lbl" style={{ marginTop: 3 }}>
                    Include your non-private deployed bots on the public Leaderboard.
                  </div>
                </div>
                <Segmented
                  ariaLabel="Leaderboard visibility"
                  value={botsOnBoard ? "shown" : "hidden"}
                  onChange={(v) => setBotsOnBoard(v === "shown")}
                  options={[
                    { value: "shown", label: "Shown" },
                    { value: "hidden", label: "Hidden" },
                  ]}
                />
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, paddingTop: 12, borderTop: "1px solid var(--line)" }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 500 }}>Broadcast activity to feed</div>
                  <div className="lbl" style={{ marginTop: 3 }}>
                    Stream your non-private bots to the global feed. A <b>Public</b> bot shows live entries, exits and kill-switches; a <b>Results</b> bot shows closed trades only; a <b>Private</b> bot never appears. Off silences all of them at once.
                  </div>
                </div>
                <Segmented
                  ariaLabel="Feed broadcast"
                  value={shareToFeed ? "on" : "off"}
                  onChange={(v) => setShareToFeed(v === "on")}
                  options={[
                    { value: "on", label: "On" },
                    { value: "off", label: "Off" },
                  ]}
                />
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, paddingTop: 12, borderTop: "1px solid var(--line)" }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 500 }}>Assistant</div>
                  <div className="lbl" style={{ marginTop: 3 }}>
                    The chart-aware helper in the corner that answers questions and drafts bots.
                  </div>
                </div>
                <Segmented
                  ariaLabel="Assistant"
                  value={assistant.enabled ? "on" : "off"}
                  onChange={(v) => assistant.setEnabled(v === "on")}
                  options={[
                    { value: "on", label: "On" },
                    { value: "off", label: "Off" },
                  ]}
                />
              </div>
            </div>
          </div>
        )}

        {tab === "Defaults" && (
          <div style={{ width: "100%", maxWidth: FORM_W, display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="card" style={{ padding: 20 }}>
              <div style={{ fontSize: 15, fontWeight: 500 }}>Bot defaults</div>
              <div className="lbl" style={{ marginTop: 6, lineHeight: 1.5 }}>Starting capital, concurrency and drawdown thresholds for new bots.</div>
              <Field label="Starting capital" value="$10,000" />
              <Field label="Max concurrent" value="6" />
              <Field label="Drawdown threshold" value="-5%" />
            </div>
          </div>
        )}

        {tab === "Fleets" && <FleetsPanel />}

        {tab === "Plan" && <PlanPanel fleetCount={fleets.length || 1} />}

        {tab === "System" && (
          <div style={{ width: "100%", maxWidth: FORM_W, display: "flex", flexDirection: "column", gap: 20 }}>
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
          <div style={{ width: "100%", maxWidth: FORM_W, display: "flex", flexDirection: "column", gap: 16 }}>
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
      {cropFile && (
        <AvatarCropper file={cropFile} busy={uploading} onCancel={() => setCropFile(null)} onSave={onCropped} />
      )}
    </>
  );
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return iso.slice(0, 10);
  }
}

// Real subscription panel: mirrors the user's Stripe state and offers the right
// action (start trial / manage / fix payment). Reached at /settings?tab=Plan,
// which is also where Stripe returns after checkout.
function PlanPanel({ fleetCount }: { fleetCount: number }) {
  const { subscription, subLoading, refreshSubscription } = useAuth();
  const [sp] = useSearchParams();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const justCheckedOut = sp.get("checkout") === "success";
  const ent = entitlementOf(subscription);

  // On arrival (and especially right after checkout) re-read the mirror; the
  // webhook usually lands within a second or two, so poll a couple more times.
  useEffect(() => {
    void refreshSubscription();
    if (!justCheckedOut) return;
    const t1 = setTimeout(() => void refreshSubscription(), 2500);
    const t2 = setTimeout(() => void refreshSubscription(), 6000);
    return () => { clearTimeout(t1); clearTimeout(t2); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const subscribe = async () => {
    setBusy(true); setErr(null);
    const { error } = await startCheckout();
    if (error) { setErr(error); setBusy(false); }
  };
  const manage = async () => {
    setBusy(true); setErr(null);
    const { error } = await openBillingPortal();
    if (error) { setErr(error); setBusy(false); }
  };

  const chip = ent.trialing
    ? { label: `Trial · ${ent.daysLeft}d left`, dot: "liveDot" }
    : ent.status === "active"
      ? { label: ent.cancelAtPeriodEnd ? "Active · ending" : "Active", dot: "liveDot" }
      : ent.pastDue
        ? { label: "Payment failed", dot: "downDot" }
        : ent.status === "canceled"
          ? { label: "Canceled", dot: "downDot" }
          : { label: "No plan", dot: "downDot" };

  return (
    <div style={{ width: "100%", maxWidth: FORM_W, display: "flex", flexDirection: "column", gap: 16 }}>
      {justCheckedOut && !ent.entitled && (
        <div className="card" style={{ padding: 14, fontSize: 13, color: "var(--muted)" }}>
          Finalizing your trial — this can take a few seconds.
          <button
            style={{ marginLeft: 6, background: "none", border: "none", color: "#8BB4E8", cursor: "pointer", padding: 0 }}
            onClick={() => void refreshSubscription()}
          >
            Refresh
          </button>
        </div>
      )}
      <div className="card" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ fontSize: 15, fontWeight: 500 }}>Paper Fleet {ent.entitled ? "Pro" : "— Free"}</div>
          <span className="chip"><span className={chip.dot} />{chip.label}</span>
        </div>
        <div className="lbl" style={{ lineHeight: 1.5 }}>
          {ent.entitled
            ? `Full access — ${PRICE_LABEL}${PRICE_PERIOD}.`
            : ent.trialAvailable
              ? `Unlimited bots, multiple fleets, feed signals and the AI co-pilot — ${PRICE_LABEL}${PRICE_PERIOD}, after a ${TRIAL_DAYS}-day free trial.`
              : `Unlimited bots, multiple fleets, feed signals and the AI co-pilot — ${PRICE_LABEL}${PRICE_PERIOD}.`}
        </div>

        {ent.trialing && (
          <Field label="Trial ends" value={subscription?.trial_ends_at ? fmtDate(subscription.trial_ends_at) : "—"} />
        )}
        {ent.status === "active" && (
          <Field
            label={ent.cancelAtPeriodEnd ? "Access until" : "Renews"}
            value={subscription?.current_period_end ? fmtDate(subscription.current_period_end) : "—"}
          />
        )}
        <Field label="Fleets" value={String(fleetCount)} />
        <Field label="Bots" value="Unlimited (paper)" />

        {subLoading ? null : ent.entitled ? (
          <button className={`${p.btn} ${p.sm}`} style={{ alignSelf: "flex-start" }} disabled={busy} onClick={() => void manage()}>
            {busy ? "Opening…" : "Manage billing"}
          </button>
        ) : ent.pastDue ? (
          <button className={`${p.btn} ${p.pri}`} style={{ alignSelf: "flex-start", height: 40 }} disabled={busy} onClick={() => void manage()}>
            {busy ? "Opening…" : "Update payment"}
          </button>
        ) : (
          <button className={`${p.btn} ${p.pri}`} style={{ alignSelf: "flex-start", height: 40 }} disabled={busy} onClick={() => void subscribe()}>
            {busy ? "Opening checkout…" : ent.trialAvailable ? `Start ${TRIAL_DAYS}-day free trial` : "Upgrade to Pro"}
          </button>
        )}
        {err && <div style={{ color: "var(--down)", fontSize: 13 }}>{err}</div>}
      </div>
    </div>
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
