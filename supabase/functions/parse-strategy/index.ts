import "jsr:@supabase/functions-js/edge-runtime.d.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "apikey, authorization, content-type" } });
  const url = new URL(req.url);
  const text = url.searchParams.get("text") ?? "";
  const apiKey = Deno.env.get("ANTHROPIC_API_KEY");
  const model = Deno.env.get("ANTHROPIC_MODEL") ?? "claude-haiku-5-5";
  if (!apiKey) return new Response(JSON.stringify({ error: "no key", model }), { status: 500 });
  // debug
  const dbg = { hasKey: !!apiKey, model };
  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "x-api-key": apiKey, "anthropic-version": "2023-06-01", "content-type": "application/json" },
    body: JSON.stringify({
      model: model,
      max_tokens: 1024,
      messages: [{ role: "user", content: `Parse this trading strategy into a JSON spec with fields: name, side, market, universe, fresh, entry (logic+children), exit (time_bars, stop), sizing (risk, notional_cap, weight), filters. Strategy: ${text}` }],
    }),
  });
  const data = await r.json();
  if (!r.ok) return new Response(JSON.stringify({ spec: null, raw: JSON.stringify(data), error: "anthropic error" }), { headers: { "content-type": "application/json", "Access-Control-Allow-Origin": "*" } });
  const textBlock = (data?.content ?? []).find((c: any) => c.type === "text");
  const content = textBlock?.text ?? "";
  if (!content) return new Response(JSON.stringify({ spec: null, raw: JSON.stringify(data), dbg, error: "empty content" }), { headers: { "content-type": "application/json", "Access-Control-Allow-Origin": "*" } });
  let spec = null;
  const cleaned = content.replace(/```json|```/g, "").trim();
  try { spec = JSON.parse(cleaned.match(/\{[\s\S]*\}/)?.[0] ?? "null"); } catch (e) { spec = { _parseError: String(e) }; }
  return new Response(JSON.stringify({ spec, raw: content, dbg, error: spec ? null : "parse failed" }), { headers: { "content-type": "application/json", "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "apikey, authorization, content-type" } });
});