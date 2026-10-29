import "jsr:@supabase/functions-js/edge-runtime.d.ts";

// Paper Fleet's site-wide assistant. Grounded in the real data the client sends
// (the current page/chart context), can search the web for current events, never
// promises returns, and lands at "build a bot and let the market judge" — it
// proposes a testable strategy via propose_strategy, which the web turns into a
// Builder hand-off. Streams its reply as newline-delimited JSON events.

const SYSTEM_PROMPT = `You are the Paper Fleet assistant — a sharp, concise companion in a product where users build trading bots in plain English, prove them on paper, and deploy the ones that earn it. You're a chat bubble: keep replies to a few sentences.

The context below is what the user is looking at — the page, an "On screen" summary of what's rendered (names, prices, rankings, feed items), and when they're on a coin: candles, 24h stats, news, and a computed Indicators block (RSI, EMA, ATR, ROC, realized volatility, range position). Work from it directly. When asked about an indicator, quote the real value from the Indicators block — do not eyeball or guess it. Those values are indicative over the shown window; the backtest recomputes precisely over full history. There is no live volume feed, so never quote volume-based indicators (VOL_RATIO, OBV, MFI, VWAP) as current values. State facts plainly; never invent a cause for a move. If the data and news don't explain something, or the user asks about current events, use web_search — prefer the provided news first, and cite the source. Only say you lack data when neither the context nor a search turns anything up.

You are not a financial advisor: never promise or imply profit or that a strategy will work. The honest answer to "will this make money?" is "that's what the backtest and paper trading are for — let's build it and let the market judge."

When the user wants to catch or trade a pattern, COLLECT the full strategy with them, then call propose_strategy with a COMPLETE plain-English description that leaves nothing implicit. It's fed verbatim into the same parser that works when a user types a strategy into the Builder, so spell out: side (long/short); market + instrument(s) or universe; timeframe; EVERY entry condition in order; any time-of-day / day-of-week window (state it in UTC — convert sessions yourself: Tokyo 09:00 JST = 00:00 UTC, London = 07:00–08:00 UTC, NY 09:30 ET ≈ 13:30/14:30 UTC — and say "weekdays" rather than listing numbers); and the exits (max hold, stop %, take-profit %).

If a key detail is ambiguous (e.g. "the market open" — which session?), ASK a quick clarifying question before proposing. A recurring timing window trades EVERY matching day, not a single date — if the user wants a one-off event, say so; you can't encode a calendar date as a repeating filter. The engine can use: price (close/open/high/low/volume), ROC, VOL_RATIO, WICK_FRAC, CLOSE_POS, RSI, EMA, SMA, ATR, NATR, ADX, CCI, MFI, WILLR, MACD, Bollinger Bands — no news-based or discretionary entries. On fx_spot there is no volume, so don't use volume indicators there.`;

const TOOLS = [
  { type: "web_search_20250305", name: "web_search", max_uses: 3 },
  {
    name: "propose_strategy",
    description:
      "Propose a trading strategy. Pass a short name plus a COMPLETE plain-English description — it is fed verbatim into the strategy parser (the exact path that works when a user types a strategy into the Builder), so it must fully specify the strategy with nothing left implicit.",
    input_schema: {
      type: "object",
      properties: {
        name: { type: "string", description: "Short bot name, max 28 chars." },
        description: {
          type: "string",
          description:
            "The complete strategy in plain English: side (long/short), market and instrument(s) or universe, timeframe, EVERY entry condition, any time-of-day/day-of-week window, and the exits (max hold, stop %, take-profit %). Be explicit and unambiguous — e.g. \"Long BTC and ETH on crypto, 1h, when EMA50 is above EMA200 and ADX(14) is above 20 and RSI(14) crosses above 35 and close is above EMA20 and MACD crosses above its signal; only 13:00-17:00 UTC on weekdays; exit after 48 bars or a 8% stop or a 6% take-profit.\"",
        },
      },
      required: ["name", "description"],
    },
  },
];

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "apikey, authorization, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

const f = (n: number | null, d = 2) => (n == null || !isFinite(n) ? "?" : Number(n).toFixed(d));

// Indicator snapshot computed from the candles in view. Indicative (over the
// shown window only) — the engine recomputes precisely over full history for a
// backtest. No volume in the chart feed, so volume-based indicators are omitted.
function indicatorSnapshot(candles: any[]): string {
  const c = candles.filter((k) => typeof k.c === "number" && typeof k.h === "number" && typeof k.l === "number");
  const n = c.length;
  if (n < 20) return "";
  const close = c.map((k) => k.c), high = c.map((k) => k.h), low = c.map((k) => k.l);
  const last = close[n - 1];
  const roc = (p: number) => (n > p ? (last / close[n - 1 - p] - 1) * 100 : null);
  const sma = (p: number) => (n >= p ? close.slice(n - p).reduce((a, b) => a + b, 0) / p : null);
  const ema = (p: number) => {
    if (n < p) return null;
    const k = 2 / (p + 1);
    let e = close.slice(0, p).reduce((a, b) => a + b, 0) / p;
    for (let i = p; i < n; i++) e = close[i] * k + e * (1 - k);
    return e;
  };
  const rsi = (p = 14) => {
    if (n <= p) return null;
    let g = 0, l = 0;
    for (let i = 1; i <= p; i++) {
      const d = close[i] - close[i - 1];
      d >= 0 ? (g += d) : (l -= d);
    }
    g /= p; l /= p;
    for (let i = p + 1; i < n; i++) {
      const d = close[i] - close[i - 1];
      g = (g * (p - 1) + Math.max(d, 0)) / p;
      l = (l * (p - 1) + Math.max(-d, 0)) / p;
    }
    return l === 0 ? 100 : 100 - 100 / (1 + g / l);
  };
  const atr = (p = 14) => {
    if (n <= p) return null;
    const tr: number[] = [];
    for (let i = 1; i < n; i++) tr.push(Math.max(high[i] - low[i], Math.abs(high[i] - close[i - 1]), Math.abs(low[i] - close[i - 1])));
    if (tr.length < p) return null;
    let a = tr.slice(0, p).reduce((x, y) => x + y, 0) / p;
    for (let i = p; i < tr.length; i++) a = (a * (p - 1) + tr[i]) / p;
    return a;
  };
  const rets: number[] = [];
  for (let i = Math.max(1, n - 20); i < n; i++) rets.push(close[i] / close[i - 1] - 1);
  const mean = rets.reduce((a, b) => a + b, 0) / (rets.length || 1);
  const vol = Math.sqrt(rets.reduce((a, b) => a + (b - mean) ** 2, 0) / (rets.length || 1)) * 100;
  const win = close.slice(Math.max(0, n - 20));
  const hi = Math.max(...win), lo = Math.min(...win);
  const pos = hi > lo ? ((last - lo) / (hi - lo)) * 100 : 50;
  const e20 = ema(20), a = atr(14);
  const d = last < 10 ? 4 : 2;
  return [
    `last close ${f(last, d)}`,
    `ROC: 8-bar ${f(roc(8))}%, 16-bar ${f(roc(16))}%`,
    `RSI(14) ${f(rsi(), 1)}`,
    `SMA20 ${f(sma(20), d)}, EMA20 ${f(e20, d)}, EMA50 ${f(ema(50), d)}${e20 != null ? ` — price ${last >= e20 ? "above" : "below"} EMA20` : ""}`,
    `ATR(14) ${f(a, d)}${a != null ? ` (${f((a / last) * 100)}% of price)` : ""}`,
    `realized vol (20-bar) ${f(vol)}% per bar`,
    `position in last-20 range ${f(pos, 0)}% (hi ${f(hi, d)}, lo ${f(lo, d)})`,
  ].join("\n");
}

function contextBlock(ctx: any): string {
  if (!ctx || typeof ctx !== "object") return "No page context.";
  const lines: string[] = [];
  lines.push(`Page: ${ctx.path ?? "unknown"}`);
  if (ctx.screen && typeof ctx.screen === "object") {
    const rows = Array.isArray(ctx.screen.rows) ? ctx.screen.rows.slice(0, 20) : [];
    lines.push(`On screen — ${ctx.screen.title ?? "page"}:\n` + rows.map((r: any) => `- ${r}`).join("\n"));
  }
  if (ctx.symbol) lines.push(`Symbol in view: ${ctx.symbol}${ctx.interval ? ` (${ctx.interval} candles)` : ""}`);
  if (ctx.market) {
    const m = ctx.market;
    lines.push(
      `24h stats — price ${m.price ?? "?"}, change ${m.change_pct != null ? m.change_pct.toFixed(2) + "%" : "?"}, ` +
        `high ${m.high ?? "?"}, low ${m.low ?? "?"}, quote vol ${m.quote_volume ?? "?"}.`,
    );
  }
  if (Array.isArray(ctx.candles) && ctx.candles.length) {
    const c = ctx.candles.slice(-48);
    lines.push(
      `Recent ${c.length} candles (t=unix ms, o/h/l/c):\n` +
        c.map((k: any) => `${k.t}: o${k.o} h${k.h} l${k.l} c${k.c}`).join("\n"),
    );
    const ind = indicatorSnapshot(ctx.candles);
    if (ind) {
      lines.push(
        `Indicators (computed from the candles above — indicative over this window; the backtest recomputes precisely over full history):\n${ind}`,
      );
    }
  }
  if (ctx.focus && typeof ctx.focus === "object") {
    const fo = ctx.focus;
    lines.push(
      `The user clicked a specific candle — treat "here", "this candle", "this point", "at this time" as THIS bar: ` +
        `${fo.iso} (${fo.barsAgo} bars ago), o${fo.o} h${fo.h} l${fo.l} c${fo.c}. ` +
        `Describe what happened on/around it using the surrounding candles.`,
    );
  }
  if (Array.isArray(ctx.news) && ctx.news.length) {
    lines.push("Recent news headlines:\n" + ctx.news.slice(0, 8).map((n: any) => `- ${n.title}`).join("\n"));
  }
  return lines.join("\n");
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
  const apiKey = Deno.env.get("ANTHROPIC_API_KEY");
  const model = Deno.env.get("ANTHROPIC_CHAT_MODEL") ?? "claude-sonnet-5";
  const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...CORS } });

  if (!apiKey) return json({ error: "ANTHROPIC_API_KEY not configured" }, 500);
  if (req.method !== "POST") return json({ error: "POST only" }, 405);

  let payload: any;
  try {
    payload = await req.json();
  } catch {
    return json({ error: "Invalid JSON body" }, 400);
  }
  const history = Array.isArray(payload?.messages) ? payload.messages : [];
  const messages = history
    .filter((m: any) => (m?.role === "user" || m?.role === "assistant") && typeof m?.content === "string" && m.content.trim())
    .slice(-12)
    .map((m: any) => ({ role: m.role, content: m.content }));
  if (!messages.length) return json({ error: "No messages" }, 400);

  const system = `${SYSTEM_PROMPT}\n\n--- Current context ---\n${contextBlock(payload?.context)}`;

  const upstream = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
    },
    body: JSON.stringify({ model, max_tokens: 1500, system, tools: TOOLS, messages, stream: true }),
  });
  if (!upstream.ok || !upstream.body) {
    const err = await upstream.json().catch(() => null);
    return json({ error: err?.error?.message ?? "Anthropic API error" });
  }

  // Parse Anthropic's SSE stream and re-emit compact NDJSON events to the client:
  //   {"type":"text","v":"…"}  {"type":"status","v":"…"}  {"type":"proposal","v":{…}}
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  const stream = new ReadableStream({
    async start(ctrl) {
      const emit = (o: unknown) => ctrl.enqueue(encoder.encode(JSON.stringify(o) + "\n"));
      const blocks: Record<number, { type?: string; name?: string; json: string }> = {};
      let buf = "";
      const reader = upstream.body!.getReader();
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const parts = buf.split("\n\n");
          buf = parts.pop() ?? "";
          for (const part of parts) {
            const dataLine = part.split("\n").find((l) => l.startsWith("data:"));
            if (!dataLine) continue;
            const raw = dataLine.slice(5).trim();
            if (!raw || raw === "[DONE]") continue;
            let ev: any;
            try {
              ev = JSON.parse(raw);
            } catch {
              continue;
            }
            if (ev.type === "content_block_start") {
              const cb = ev.content_block ?? {};
              blocks[ev.index] = { type: cb.type, name: cb.name, json: "" };
              if (cb.type === "server_tool_use" && cb.name === "web_search") emit({ type: "status", v: "Searching the web…" });
            } else if (ev.type === "content_block_delta") {
              const d = ev.delta ?? {};
              if (d.type === "text_delta" && d.text) emit({ type: "text", v: d.text });
              else if (d.type === "input_json_delta") {
                const b = blocks[ev.index];
                if (b) b.json += d.partial_json ?? "";
              }
            } else if (ev.type === "content_block_stop") {
              const b = blocks[ev.index];
              if (b && b.type === "tool_use" && b.name === "propose_strategy") {
                try {
                  const inp = JSON.parse(b.json || "{}");
                  // description is the complete strategy text; the Builder feeds
                  // it to the same parser the manual box uses.
                  emit({
                    type: "proposal",
                    v: { name: String(inp.name ?? "New bot").slice(0, 28), description: String(inp.description ?? "") },
                  });
                } catch {
                  /* ignore malformed tool json */
                }
              }
            }
          }
        }
      } catch {
        emit({ type: "error", v: "stream interrupted" });
      }
      ctrl.close();
    },
  });

  return new Response(stream, { headers: { "content-type": "application/x-ndjson", ...CORS } });
});
