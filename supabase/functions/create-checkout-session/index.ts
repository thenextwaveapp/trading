import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import Stripe from "npm:stripe@^17";
import { createClient } from "npm:@supabase/supabase-js@^2";

// Opens a Stripe Checkout session for the $27/mo "pro" plan with a 7-day trial.
// Caller must be an authenticated Paper Fleet user (we bind the Stripe customer
// to their auth.uid so the webhook can mirror status back to pf_subscriptions).

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "apikey, authorization, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS, "Content-Type": "application/json" },
  });

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ error: "method not allowed" }, 405);

  const stripeKey = Deno.env.get("STRIPE_SECRET_KEY");
  const priceId = Deno.env.get("STRIPE_PRICE_ID");
  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!stripeKey || !priceId || !supabaseUrl || !anonKey || !serviceKey) {
    return json({ error: "billing not configured" }, 500);
  }

  // Identify the caller from their JWT (anon client + the caller's bearer token).
  const authHeader = req.headers.get("Authorization") ?? "";
  const userClient = createClient(supabaseUrl, anonKey, {
    global: { headers: { Authorization: authHeader } },
  });
  const { data: { user }, error: userErr } = await userClient.auth.getUser();
  if (userErr || !user) return json({ error: "not authenticated" }, 401);

  const stripe = new Stripe(stripeKey, {
    httpClient: Stripe.createFetchHttpClient(),
  });
  // Service client writes the stripe_customer_id back onto the profile.
  const admin = createClient(supabaseUrl, serviceKey);

  // Find or create this user's Stripe customer (one per profile).
  const { data: profile } = await admin
    .from("pf_profiles")
    .select("stripe_customer_id, email")
    .eq("id", user.id)
    .single();

  let customerId = profile?.stripe_customer_id as string | null | undefined;
  if (!customerId) {
    const customer = await stripe.customers.create({
      email: profile?.email ?? user.email ?? undefined,
      metadata: { owner: user.id },
    });
    customerId = customer.id;
    await admin.from("pf_profiles").update({ stripe_customer_id: customerId }).eq("id", user.id);
  }

  // Where to send the user back. Prefer the app origin that called us.
  const origin = req.headers.get("Origin") ?? Deno.env.get("APP_URL") ?? "";
  let returnTo = "/settings?tab=Plan";
  try {
    const body = await req.json();
    if (body && typeof body.returnTo === "string") returnTo = body.returnTo;
  } catch { /* no body is fine */ }

  // The 7-day free trial is one-time: grant it only if this account has never
  // had a subscription. A returning subscriber checks out at the paid price.
  const { data: priorSub } = await admin
    .from("pf_subscriptions")
    .select("id")
    .eq("owner", user.id)
    .maybeSingle();
  const trialAvailable = !priorSub;

  const session = await stripe.checkout.sessions.create({
    mode: "subscription",
    customer: customerId,
    line_items: [{ price: priceId, quantity: 1 }],
    subscription_data: {
      ...(trialAvailable ? { trial_period_days: 7 } : {}),
      metadata: { owner: user.id },
    },
    client_reference_id: user.id,
    allow_promotion_codes: true,
    success_url: `${origin}${returnTo}${returnTo.includes("?") ? "&" : "?"}checkout=success`,
    cancel_url: `${origin}${returnTo}${returnTo.includes("?") ? "&" : "?"}checkout=cancelled`,
  });

  return json({ url: session.url });
});
