import { supabase } from "../db/supabase";
import type { DbSubscription } from "../db/types";

// $27/mo, 7-day trial. The price itself lives in Stripe; this is just the
// display copy the UI reuses so it never drifts across screens.
export const PRICE_LABEL = "$27";
export const PRICE_PERIOD = "/mo";
export const TRIAL_DAYS = 7;

// Free-plan caps (Pro removes both). Mirror of the `free` pf_plans row.
export const FREE_MAX_FLEETS = 1;
export const FREE_MAX_DEPLOYED = 3;

// Stripe sends the browser back here after checkout/portal. Always the Plan tab:
// it's auth-gated (not plan-gated), so the user never bounces back to the paywall
// while the webhook is still mirroring the new subscription. Note the /#/ — the
// app is a HashRouter, and this string is appended to window.location.origin.
export const BILLING_RETURN = "/#/settings?tab=Plan";

export interface Entitlement {
  entitled: boolean;        // may use the Pro feature set (trial or paid)
  status: DbSubscription["status"] | "none";
  trialing: boolean;
  pastDue: boolean;
  daysLeft: number;         // whole days left in the current trial/period
  cancelAtPeriodEnd: boolean;
  trialAvailable: boolean;  // never subscribed → the one-time free trial is on the table
}

const daysUntil = (iso: string | null): number => {
  if (!iso) return 0;
  const ms = new Date(iso).getTime() - Date.now();
  return Math.max(0, Math.ceil(ms / 86_400_000));
};

// The single source of truth for "can this user use the app". trialing + active
// are in; everything else (past_due, canceled, none) is out. We read the local
// mirror of Stripe, so this is synchronous and cheap.
export function entitlementOf(sub: DbSubscription | null): Entitlement {
  if (!sub) {
    // No row has ever existed → never subscribed → the one-time trial is available.
    return { entitled: false, status: "none", trialing: false, pastDue: false, daysLeft: 0, cancelAtPeriodEnd: false, trialAvailable: true };
  }
  const trialing = sub.status === "trialing";
  const entitled = sub.status === "active" || trialing || sub.status === "past_due";
  const end = trialing ? sub.trial_ends_at : sub.current_period_end;
  return {
    entitled,
    status: sub.status,
    trialing,
    pastDue: sub.status === "past_due",
    daysLeft: daysUntil(end),
    cancelAtPeriodEnd: sub.cancel_at_period_end,
    // A row exists → the free trial has already been consumed; re-subscribe is paid.
    trialAvailable: false,
  };
}

// Open Stripe Checkout (7-day trial → $27/mo) and send the browser there.
// supabase.functions.invoke attaches the caller's JWT, which the edge function
// verifies before binding the Stripe customer to this user.
export async function startCheckout(returnTo: string = BILLING_RETURN): Promise<{ error: string | null }> {
  const { data, error } = await supabase.functions.invoke("create-checkout-session", {
    body: { returnTo },
  });
  if (error) return { error: error.message };
  if (data?.url) {
    window.location.href = data.url as string;
    return { error: null };
  }
  return { error: (data?.error as string) ?? "Could not start checkout." };
}

// Open the Stripe Customer Portal (manage card / invoices / cancel).
export async function openBillingPortal(returnTo: string = BILLING_RETURN): Promise<{ error: string | null }> {
  const { data, error } = await supabase.functions.invoke("create-portal-session", {
    body: { returnTo },
  });
  if (error) return { error: error.message };
  if (data?.url) {
    window.location.href = data.url as string;
    return { error: null };
  }
  return { error: (data?.error as string) ?? "Could not open billing." };
}
