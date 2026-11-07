import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import Stripe from "npm:stripe@^17";
import { createClient } from "npm:@supabase/supabase-js@^2";

// Stripe → pf_subscriptions mirror. Stripe is the source of truth for billing;
// this is the ONLY writer of the mirror the app gates on. Verifies the webhook
// signature, resolves the owning user, and upserts one row per owner. Runs with
// the service role so it bypasses the owner-only RLS on pf_subscriptions.

const iso = (unixSeconds: number | null | undefined) =>
  unixSeconds ? new Date(unixSeconds * 1000).toISOString() : null;

Deno.serve(async (req) => {
  if (req.method !== "POST") return new Response("method not allowed", { status: 405 });

  const stripeKey = Deno.env.get("STRIPE_SECRET_KEY");
  const webhookSecret = Deno.env.get("STRIPE_WEBHOOK_SECRET");
  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!stripeKey || !webhookSecret || !supabaseUrl || !serviceKey) {
    return new Response("billing not configured", { status: 500 });
  }

  const stripe = new Stripe(stripeKey, {
    httpClient: Stripe.createFetchHttpClient(),
  });

  const sig = req.headers.get("stripe-signature");
  if (!sig) return new Response("missing signature", { status: 400 });

  const payload = await req.text();
  let event: Stripe.Event;
  try {
    // Async variant: edge/Deno verifies with SubtleCrypto, not Node crypto.
    event = await stripe.webhooks.constructEventAsync(
      payload, sig, webhookSecret, undefined, Stripe.createSubtleCryptoProvider(),
    );
  } catch (err) {
    return new Response(`signature check failed: ${err}`, { status: 400 });
  }

  const admin = createClient(supabaseUrl, serviceKey);

  // Map a Stripe subscription to the owning Paper Fleet user: prefer the owner
  // stamped in metadata at checkout, else fall back to the stored customer id.
  const resolveOwner = async (sub: Stripe.Subscription): Promise<string | null> => {
    const metaOwner = sub.metadata?.owner;
    if (metaOwner) return metaOwner;
    const customerId = typeof sub.customer === "string" ? sub.customer : sub.customer?.id;
    if (!customerId) return null;
    const { data } = await admin
      .from("pf_profiles")
      .select("id")
      .eq("stripe_customer_id", customerId)
      .single();
    return data?.id ?? null;
  };

  const upsert = async (sub: Stripe.Subscription) => {
    const owner = await resolveOwner(sub);
    if (!owner) return; // unknown customer — nothing to mirror
    const customerId = typeof sub.customer === "string" ? sub.customer : sub.customer?.id ?? null;
    if (customerId) {
      await admin.from("pf_profiles")
        .update({ stripe_customer_id: customerId })
        .eq("id", owner)
        .is("stripe_customer_id", null);
    }
    const periodEnd = iso(sub.current_period_end);
    await admin.from("pf_subscriptions").upsert({
      owner,
      plan_key: "pro",
      status: sub.status,
      stripe_subscription_id: sub.id,
      trial_ends_at: iso(sub.trial_end),
      current_period_end: periodEnd,
      cancel_at_period_end: sub.cancel_at_period_end ?? false,
      renewal_date: periodEnd ? periodEnd.slice(0, 10) : null,
      updated_at: new Date().toISOString(),
    }, { onConflict: "owner" });
  };

  switch (event.type) {
    case "customer.subscription.created":
    case "customer.subscription.updated":
    case "customer.subscription.deleted":
    case "customer.subscription.paused":
    case "customer.subscription.resumed":
      await upsert(event.data.object as Stripe.Subscription);
      break;
    case "checkout.session.completed": {
      // Pull the fresh subscription so the mirror is correct even if the
      // subscription.* event is delayed or arrives out of order.
      const session = event.data.object as Stripe.Checkout.Session;
      if (session.subscription) {
        const subId = typeof session.subscription === "string"
          ? session.subscription : session.subscription.id;
        const sub = await stripe.subscriptions.retrieve(subId);
        if (session.client_reference_id && !sub.metadata?.owner) {
          sub.metadata = { ...sub.metadata, owner: session.client_reference_id };
        }
        await upsert(sub);
      }
      break;
    }
    default:
      break; // ignore everything else
  }

  return new Response(JSON.stringify({ received: true }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
});
