import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import Stripe from "npm:stripe@^17";
import { createClient } from "npm:@supabase/supabase-js@^2";

// Opens the Stripe Customer Portal so a subscriber can update their card, see
// invoices, or cancel. Caller must be authenticated and already have a Stripe
// customer (created at first checkout).

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
  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!stripeKey || !supabaseUrl || !anonKey || !serviceKey) {
    return json({ error: "billing not configured" }, 500);
  }

  const authHeader = req.headers.get("Authorization") ?? "";
  const userClient = createClient(supabaseUrl, anonKey, {
    global: { headers: { Authorization: authHeader } },
  });
  const { data: { user }, error: userErr } = await userClient.auth.getUser();
  if (userErr || !user) return json({ error: "not authenticated" }, 401);

  const admin = createClient(supabaseUrl, serviceKey);
  const { data: profile } = await admin
    .from("pf_profiles")
    .select("stripe_customer_id")
    .eq("id", user.id)
    .single();

  const customerId = profile?.stripe_customer_id as string | null | undefined;
  if (!customerId) return json({ error: "no billing account yet" }, 400);

  const origin = req.headers.get("Origin") ?? Deno.env.get("APP_URL") ?? "";
  let returnTo = "/settings?tab=Plan";
  try {
    const body = await req.json();
    if (body && typeof body.returnTo === "string") returnTo = body.returnTo;
  } catch { /* no body is fine */ }

  const stripe = new Stripe(stripeKey, {
    httpClient: Stripe.createFetchHttpClient(),
  });
  const session = await stripe.billingPortal.sessions.create({
    customer: customerId,
    return_url: `${origin}${returnTo}`,
  });

  return json({ url: session.url });
});
