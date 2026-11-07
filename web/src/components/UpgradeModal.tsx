import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import Logo from "./Logo";
import { createPortal } from "react-dom";
import { useAuth } from "../auth";
import { entitlementOf, startCheckout, PRICE_LABEL, PRICE_PERIOD, TRIAL_DAYS } from "../lib/billing";
import p from "../routes/pages.module.css";

interface UpgradeApi {
  /** Open the Pro modal. `reason` is an optional one-liner for the context that triggered it. */
  open: (reason?: string) => void;
  close: () => void;
}

const Ctx = createContext<UpgradeApi | null>(null);

export function useUpgrade(): UpgradeApi {
  const v = useContext(Ctx);
  if (!v) throw new Error("useUpgrade must be used within <UpgradeProvider>");
  return v;
}

const PERKS = [
  "Unlimited deployed bots and multiple fleets",
  "Feed & social-signal strategies",
  "The AI co-pilot, unlimited",
];

// A pull, not a push: nothing renders until something calls open() — e.g. a user
// reaching for a Pro feature. Never auto-interrupts. Entitled users can't see it.
export function UpgradeProvider({ children }: { children: ReactNode }) {
  const { subscription } = useAuth();
  const [state, setState] = useState<{ reason?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const api = useMemo<UpgradeApi>(
    () => ({ open: (reason?: string) => { setErr(null); setState({ reason }); }, close: () => setState(null) }),
    [],
  );

  const ent = entitlementOf(subscription);
  const show = state !== null && !ent.entitled;

  const go = useCallback(async () => {
    setBusy(true);
    setErr(null);
    const { error } = await startCheckout(); // server decides trial vs immediate paid
    if (error) { setErr(error); setBusy(false); }
  }, []);

  return (
    <Ctx.Provider value={api}>
      {children}
      {show && createPortal(
        <div
          className="ovl"
          style={{ zIndex: 80, display: "flex", alignItems: "center", justifyContent: "center", padding: 24, overflowY: "auto" }}
          onClick={() => setState(null)}
        >
          <div
            className="glass"
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "min(540px, 94vw)", padding: "44px 48px 36px",
              display: "flex", flexDirection: "column", alignItems: "center",
              gap: 24, textAlign: "center", borderRadius: 20,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <Logo size={26} />
              <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 23, letterSpacing: "-0.04em" }}>
                paper fleet
              </span>
            </div>

            <div>
              {state?.reason && (
                <div className="lbl" style={{ fontSize: 13, marginBottom: 10 }}>{state.reason}</div>
              )}
              <h1 className={p.title} style={{ fontSize: 32, lineHeight: 1.12 }}>
                {ent.trialAvailable ? `Start your ${TRIAL_DAYS}-day free trial` : "Upgrade to Pro"}
              </h1>
              <div className={p.subtitle} style={{ marginTop: 12, maxWidth: 400 }}>
                {ent.trialAvailable
                  ? <>Unlock everything for {TRIAL_DAYS} days. <b style={{ color: "var(--fg)" }}>{PRICE_LABEL}{PRICE_PERIOD}</b> after — cancel anytime.</>
                  : <>Full access to Paper Fleet. <b style={{ color: "var(--fg)" }}>{PRICE_LABEL}{PRICE_PERIOD}</b>, cancel anytime.</>}
              </div>
            </div>

            <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 12, textAlign: "left" }}>
              {PERKS.map((perk) => (
                <li key={perk} style={{ display: "flex", gap: 11, alignItems: "flex-start", fontSize: 14, lineHeight: 1.4 }}>
                  <span style={{ color: "var(--up)", flex: "none", marginTop: 1 }}>✓</span>
                  <span>{perk}</span>
                </li>
              ))}
            </ul>

            <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 11, marginTop: 2 }}>
              <button
                className={`${p.btn} ${p.pri}`}
                style={{ height: 50, fontSize: 15, justifyContent: "center", width: "100%" }}
                disabled={busy}
                onClick={() => void go()}
              >
                {busy ? "Opening checkout…" : ent.trialAvailable ? `Start ${TRIAL_DAYS}-day free trial` : "Upgrade to Pro"}
              </button>
              <button
                className={p.btn}
                style={{ height: 42, justifyContent: "center", width: "100%" }}
                onClick={() => setState(null)}
              >
                Maybe later
              </button>
              {err && <div style={{ color: "var(--down)", fontSize: 13 }}>{err}</div>}
              {ent.trialAvailable && (
                <div className="lbl" style={{ fontSize: 12, marginTop: 2 }}>
                  No charge until day {TRIAL_DAYS + 1}. Cancel before then and pay nothing.
                </div>
              )}
            </div>
          </div>
        </div>,
        document.body,
      )}
    </Ctx.Provider>
  );
}
