import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SYSTEM_PROMPT = `You convert plain-English trading strategies into Paper Fleet's exact JSON StrategySpec.
Return ONLY a single compact JSON object (no markdown fences, no commentary) matching this exact schema:

{
  "name": "Short descriptive bot name (max 28 chars)",
  "side": "short" | "long",
  "market": "crypto_perp" | "crypto_spot" | "equity",
  "universe": "fleet-60" | "majors" | "all-perps" | "top100-vol" | "mag-7" | "us-equities",
  "timeframe": "1m" | "5m" | "15m" | "30m" | "1h" | "4h" | "1d",
  "fresh": boolean,
  "timing": { "hours_utc": number[], "days_utc": number[] },
  "entry": {
    "logic": "AND" | "OR" | "NOT",
    "children": [
      {
        "left": { "ind": string, "params": { ... }, "offset": number } | number,
        "op": "gt" | "ge" | "lt" | "le" | "eq" | "ne" | "crosses_above" | "crosses_below",
        "right": { "ind": string, "params": { ... }, "offset": number } | number
      }
    ]
  },
  "exit": {
    "time_bars": integer (>= 1, e.g. 16 for 4h on 15m bars, 96 for 24h on 15m bars),
    "stop": {
      "mode": "none" | "hh" | "dstop" | "sig",
      "window": integer (default 16),
      "param": number (fraction, e.g. 0.02 for 2%, 0 for none)
    },
    "take_profit": number (optional fraction, e.g. 0.05 for 5%)
  },
  "sizing": {
    "risk": number (fraction, default 0.0075 for 0.75%),
    "notional_cap": number (fraction, default 0.20 for 20%),
    "weight": 1.0
  },
  "filters": []
}

Rules for indicators & operands:
- Price/volume series (params: {}): "close", "open", "high", "low", "volume". Previous bar close is {"ind": "close", "offset": -1}.
  - Red candle: {"left": {"ind": "close"}, "op": "lt", "right": {"ind": "open"}} or {"left": {"ind": "close"}, "op": "lt", "right": {"ind": "close", "offset": -1}}
  - Green candle: {"left": {"ind": "close"}, "op": "gt", "right": {"ind": "open"}}
- Custom engine indicators:
  - "ROC": Rate of change as a FRACTION (not percent!). params: {"period": int}. E.g. +12% over 16 bars -> {"left": {"ind": "ROC", "params": {"period": 16}}, "op": "ge", "right": 0.12}. Drop of 20% over 96 bars -> {"left": {"ind": "ROC", "params": {"period": 96}}, "op": "le", "right": -0.20}.
  - "VOL_RATIO": Volume multiple vs rolling mean. params: {"period": int}. E.g. volume >= 2x 8-bar average -> {"left": {"ind": "VOL_RATIO", "params": {"period": 8}}, "op": "ge", "right": 2.0}.
  - "WICK_FRAC": Upper wick fraction [0..1]. params: {"period": int}. E.g. upper wick >= 30% -> {"left": {"ind": "WICK_FRAC", "params": {"period": 16}}, "op": "ge", "right": 0.30}.
  - "CLOSE_POS": Close position in range [0..1]. params: {"period": int}. E.g. top 20% of range -> {"left": {"ind": "CLOSE_POS", "params": {"period": 16}}, "op": "ge", "right": 0.80}.
- Standard TA-Lib indicators (use "timeperiod" for period):
  - "RSI" (params: {"timeperiod": 14}, values 0..100, e.g. RSI < 30 -> right: 30)
  - "EMA", "SMA", "WMA", "DEMA", "TEMA", "KAMA" (params: {"timeperiod": 20})
  - "ATR", "NATR", "ADX", "CCI", "MFI", "WILLR", "MOM", "CMO", "RVOL" (params: {"timeperiod": 14})
  - "BBANDS_upperband", "BBANDS_middleband", "BBANDS_lowerband" (params: {"timeperiod": 20, "nbdevup": 2, "nbdevdn": 2})
  - "MACD_macd", "MACD_macdsignal", "MACD_macdhist" (params: {"fastperiod": 12, "slowperiod": 26, "signalperiod": 9})
  - "VWAP", "OBV" (params: {})
- If the user mentions stocks / equities / Mag 7 / S&P / Nasdaq / AAPL / NVDA / TSLA / SPY, set "market": "equity" and "universe": "mag-7" or "us-equities". Otherwise default to "market": "crypto_perp" and "universe": "fleet-60" (or "majors" if they ask for majors/BTC/ETH).`;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "apikey, authorization, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
  const url = new URL(req.url);
  let text = url.searchParams.get("text") ?? "";
  if (!text && req.method === "POST") {
    try {
      const body = await req.json();
      text = body?.text ?? "";
    } catch {
      /* ignore */
    }
  }
  const apiKey = Deno.env.get("ANTHROPIC_API_KEY");
  const model = Deno.env.get("ANTHROPIC_MODEL") ?? "claude-haiku-4-5";
  if (!apiKey) {
    return new Response(JSON.stringify({ error: "ANTHROPIC_API_KEY not configured", model }), {
      status: 500,
      headers: { "content-type": "application/json", ...CORS },
    });
  }

  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model,
      max_tokens: 2048,
      system: SYSTEM_PROMPT,
      messages: [{ role: "user", content: `Strategy description:\n${text}` }],
    }),
  });
  const data = await r.json();
  if (!r.ok) {
    return new Response(
      JSON.stringify({ spec: null, raw: JSON.stringify(data), error: data?.error?.message ?? "Anthropic API error" }),
      { headers: { "content-type": "application/json", ...CORS } },
    );
  }
  const textBlock = (data?.content ?? []).find((c: any) => c.type === "text");
  const content = textBlock?.text ?? "";
  if (!content) {
    return new Response(
      JSON.stringify({ spec: null, raw: JSON.stringify(data), error: "Empty response from parser" }),
      { headers: { "content-type": "application/json", ...CORS } },
    );
  }
  const cleaned = content.replace(/```json|```/g, "").trim();
  let spec: any = null;
  let parseErr: string | null = null;
  try {
    spec = JSON.parse(cleaned.match(/\{[\s\S]*\}/)?.[0] ?? "null");
  } catch (e) {
    parseErr = String(e);
  }
  if (!spec || typeof spec !== "object" || spec._parseError) {
    return new Response(
      JSON.stringify({ spec: null, raw: content, error: parseErr ?? "Could not parse strategy JSON" }),
      { headers: { "content-type": "application/json", ...CORS } },
    );
  }
  return new Response(
    JSON.stringify({ spec, raw: content, error: null }),
    { headers: { "content-type": "application/json", ...CORS } },
  );
});