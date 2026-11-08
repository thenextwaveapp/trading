import "jsr:@supabase/functions-js/edge-runtime.d.ts";

// Paper Fleet's site-wide assistant. Grounded in the real data the client sends
// (the current page/chart context), can search the web for current events, never
// promises returns, and lands at "build a bot and let the market judge" — it
// proposes a testable strategy via propose_strategy, which the web turns into a
// Builder hand-off. Streams its reply as newline-delimited JSON events.

const SYSTEM_PROMPT = `You are the Paper Fleet assistant — a sharp, concise companion in a product where users build trading bots in plain English, prove them on paper, and deploy the ones that earn it. You're a chat bubble: keep replies to a few sentences.

Your replies render as Markdown, so format for fast reading — but stay minimal. Lead with the answer in plain prose. Reach for **bold** only to mark the one or two things that matter, a short bullet or numbered list only when you're genuinely enumerating options or steps (never for a single idea), and \`inline code\` for symbols, indicator names, and numeric values (e.g. \`BTC\`, \`RSI(14)\`, \`13:00 UTC\`). No headings, no tables, no walls of text — if a paragraph says it, use a paragraph. When you ask the user to choose settings for a strategy, a tight list of the open questions reads far better than a run-on sentence.

The context below is what the user is looking at — the page, an "On screen" summary of what's rendered (names, prices, rankings, feed items), and when they're on an instrument: candles, 24h stats, news, and a computed Indicators block (RSI, EMA, ATR, ROC, realized volatility, range position). Work from it directly. When asked about an indicator, quote the real value from the Indicators block — do not eyeball or guess it. Those values are indicative over the shown window; the backtest recomputes precisely over full history. There is no live volume feed, so never quote volume-based indicators (VOL_RATIO, OBV, MFI, VWAP) as current values. State facts plainly; never invent a cause for a move. If the data and news don't explain something, or the user asks about current events, use web_search — prefer the provided news first, and cite the source. Only say you lack data when neither the context nor a search turns anything up.

You are not a financial advisor: never promise or imply profit or that a strategy will work. The honest answer to "will this make money?" is "that's what the backtest and paper trading are for — let's build it and let the market judge."

When the user wants to catch or trade a pattern, COLLECT the full strategy with them, then call propose_strategy with the COMPLETE StrategySpec JSON (the exact schema is given in the "StrategySpec schema" section below) — fill every field, leaving nothing implicit. It is applied verbatim in the Builder (no re-parse), so account for: side — long, short, OR both (a single bot CAN run a long book and a short book together; use side "both" with entry/entry_short — never tell the user they need two separate bots); market + instrument(s) or universe; timeframe; EVERY entry condition in order; any time-of-day / day-of-week window (in UTC — convert sessions yourself: Tokyo 09:00 JST = 00:00 UTC, London = 07:00–08:00 UTC, NY 09:30 ET ≈ 13:30/14:30 UTC — and use weekdays [0,1,2,3,4] rather than a single date); and the exits (max hold, stop, take-profit, and optionally a trailing stop or an exit-condition tree).

If a key detail is ambiguous (e.g. "the market open" — which session?), ASK a quick clarifying question before proposing. A recurring timing window trades EVERY matching day, not a single date — if the user wants a one-off event, say so; you can't encode a calendar date as a repeating filter. The engine triggers on price and technical indicators ONLY: price (close/open/high/low/volume), ROC, VOL_RATIO, WICK_FRAC, CLOSE_POS, RSI, EMA, SMA, ATR, NATR, ADX, CCI, MFI, WILLR, MACD, Bollinger Bands (and the other TA-Lib indicators). It has NO social-media or news feed input — do not offer or propose strategies that trigger on tweets, posts, or news headlines. If the user asks for that, say plainly the Builder can't trade on feeds yet, and steer them to a price- or indicator-based signal instead (e.g. the volatility/volume spike that usually accompanies the event).

Paper Fleet trades five markets, so always establish which one the instrument lives on (ask if unclear) and state it in the proposal: crypto, equities (stocks — e.g. AAPL, TSLA, SPY), futures, fx_spot (FX / currency pairs), and prediction. Crypto, equities and futures have full OHLCV, so any indicator is fair game. fx_spot has no volume feed — don't use volume-based indicators (VOL_RATIO, OBV, MFI, VWAP) there. Prediction markets quote only an implied-probability close (no open/high/low and no volume), so no candlestick, range or volume indicators — those contracts settle to a 0/1 outcome at expiry rather than trading a continuous price. Equities and futures also keep exchange hours, so a time-of-day window there is the regular session (NY 09:30 ET ≈ 13:30/14:30 UTC) on weekdays.`;

// The exact StrategySpec the Builder consumes — matched to what Compose's
// applyParsedSpec / normOperand actually accept (number | {ind,params,offset} |
// arith operands; no feed operands — the Builder can't represent them). The
// assistant emits this directly so the Builder applies it verbatim: no second
// model call, no re-parse, no drift.
const SPEC_SCHEMA = `A StrategySpec is a single JSON object with this exact shape. The Builder applies it verbatim, so use ONLY the fields and operands listed here:

{
  "name": "Short descriptive bot name (max 28 chars)",
  "side": "short" | "long" | "both",
  "market": "crypto_perp" | "crypto_spot" | "equity" | "futures" | "fx_spot" | "prediction",
  "universe": "fleet-60" | "majors" | "all-perps" | "top100-vol" | "mag-7" | "us-equities" | "fx-majors",
  "instruments": ["BTC", "ETH"]  (optional — BARE uppercase tickers when the strategy names specific instruments; omit for a broad preset universe),
  "timeframe": "1m" | "5m" | "15m" | "30m" | "1h" | "4h" | "1d",
  "fresh": boolean,
  "timing": { "hours_utc": number[] (0-23 UTC), "days_utc": number[] (Monday=0 .. Sunday=6, weekdays = [0,1,2,3,4]; empty = any day) },
  "entry": {
    "logic": "AND" | "OR" | "NOT",
    "children": [
      { "left": <operand>, "op": "gt" | "ge" | "lt" | "le" | "eq" | "ne" | "crosses_above" | "crosses_below", "right": <operand> }
      // a child may itself be a nested group: { "logic": ..., "children": [...] }
    ]
  },
  "entry_short": { ...same shape as "entry"... }  (ONLY when side is "both": the SHORT book's entry conditions; "entry" is then the LONG book),
  "exit": {
    "time_bars": integer (>= 1, e.g. 16 for 4h on 15m bars, 96 for 24h on 15m bars),
    "stop": { "mode": "none" | "hh" | "dstop" | "sig", "window": integer (default 16), "param": number (fraction) },
    "take_profit": number (optional fraction, e.g. 0.06 for 6%),
    "tp_close": boolean (optional — settle take-profit on the bar close instead of intrabar),
    "trailing": { "k": number (distance multiplier, e.g. 3), "natr": integer (ATR window in bars, e.g. 24) }  (optional — a stop that ratchets k×NATR behind price),
    "limit": number (optional fraction — a resting limit-exit target; omit unless the user explicitly asks for one),
    "exit_conditions": { "logic": ..., "children": [ ...same condition shape as entry... ] }  (optional — also close the position when this tree fires, after the stop/TP have had their say)
  },
  "exit_short": { ...same shape as "exit"... }  (optional, ONLY when side is "both"; defaults to the long "exit" if omitted),
  "sizing": { "risk": number (fraction, default 0.0075), "notional_cap": number (fraction, default 0.20), "weight": 1.0 },
  "filters": []
}

Dual-direction ("both"): set "side":"both" and supply BOTH books — "entry"/"exit" is the LONG side, "entry_short" (and optional "exit_short") is the SHORT side. One bot then trades both directions; reach for it whenever the user wants long AND short in a single bot (you do NOT need two separate bots).

A fixed percent stop-loss is "dstop" with param = the fraction (a 5% stop -> {"mode":"dstop","param":0.05}). "hh" trails the signal-window high + buffer, "sig" the signal-window midpoint, "none" = no stop (param 0).

An <operand> is ONE of exactly these three shapes (nothing else exists):
  - a number — e.g. 30, 0.80, -0.20
  - an indicator — { "ind": "<id>", "params": { ... }, "offset": number, "tf"?: "<timeframe>", "symbol"?: "<TICKER>" }  (offset 0 = current bar, -1 = previous bar; optional "tf" reads the indicator on another timeframe, optional "symbol" reads it on another instrument — e.g. gate alts on BTC with {"ind":"RSI","params":{"timeperiod":14},"symbol":"BTC"})
  - arithmetic over operands — { "op": "add" | "sub" | "mul" | "div", "left": <operand>, "right": <operand> }

Indicator ids & params:
- Price/volume series (params {}): "close", "open", "high", "low", "volume". Previous close = {"ind":"close","offset":-1}.
- "ROC" is a FRACTION not percent (params {"period":int}); "VOL_RATIO", "WICK_FRAC" [0..1], "CLOSE_POS" [0..1] use {"period":int}.
- TA-Lib (params use "timeperiod"): "RSI" (0..100), "EMA"/"SMA"/"WMA"/"DEMA"/"TEMA"/"KAMA", "ATR"/"NATR"/"ADX"/"CCI"/"MFI"/"WILLR"/"MOM"/"CMO"/"RVOL", "BBANDS_upperband"/"BBANDS_middleband"/"BBANDS_lowerband" (also nbdevup/nbdevdn), "MACD_macd"/"MACD_macdsignal"/"MACD_macdhist" (fastperiod/slowperiod/signalperiod), "VWAP"/"OBV".
  - "MACD crosses below its signal": {"left":{"ind":"MACD_macd","params":{"fastperiod":12,"slowperiod":26,"signalperiod":9}},"op":"crosses_below","right":{"ind":"MACD_macdsignal","params":{"fastperiod":12,"slowperiod":26,"signalperiod":9}}}.
  - "EMA20 below EMA50": {"left":{"ind":"EMA","params":{"timeperiod":20}},"op":"lt","right":{"ind":"EMA","params":{"timeperiod":50}}}.

Markets & universe:
- Equities / Mag 7 / S&P / AAPL / NVDA / TSLA / SPY -> "market":"equity", "universe":"mag-7" or "us-equities".
- FX / currency pairs -> "market":"fx_spot", "universe":"fx-majors", instruments from {EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD,NZDUSD}; no volume indicators (VOL_RATIO, OBV, MFI, VWAP) on fx_spot.
- Prediction markets quote only an implied-probability close — price-only, no OHLC/volume/range indicators there.
- Otherwise default "crypto_perp" + "fleet-60" (or "majors" for BTC/ETH).
- Named instruments go in "instruments" (BARE uppercase, no USDT) with "universe" set to the market default; broad sets use "universe" and omit "instruments".

There is NO social/news feed operand and no "thesis"/"feed" field — the Builder cannot trade on tweets, posts, or headlines. Use price and indicator conditions only.`;

const TOOLS = [
  { type: "web_search_20250305", name: "web_search", max_uses: 3 },
  {
    name: "propose_strategy",
    description:
      "Propose a trading strategy as Paper Fleet's exact JSON StrategySpec (see the StrategySpec schema in the system prompt). Fill EVERY field — side, market, universe/instruments, timeframe, the full entry condition tree, timing, and exits — leaving nothing implicit. The spec is applied verbatim in the Builder (no re-parse), so it must be complete and valid.",
    input_schema: {
      type: "object",
      properties: {
        name: { type: "string", description: "Short bot name, max 28 chars." },
        spec: {
          type: "object",
          description:
            "The complete StrategySpec JSON matching the schema in the system prompt: name, side, market, universe (and instruments when specific instruments are named), timeframe, fresh, timing, the full entry condition tree (price/indicator/arith operands only), exit, sizing, filters.",
        },
      },
      required: ["name", "spec"],
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

  const system = `${SYSTEM_PROMPT}\n\n--- StrategySpec schema (fill this for propose_strategy) ---\n${SPEC_SCHEMA}\n\n--- Current context ---\n${contextBlock(payload?.context)}`;

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
                  // spec is the complete StrategySpec; the Builder applies it
                  // verbatim — no re-parse, so clicking Build never drifts.
                  const spec = inp.spec && typeof inp.spec === "object" ? inp.spec : null;
                  if (spec) {
                    const name = String(inp.name ?? spec.name ?? "New bot").slice(0, 28);
                    emit({ type: "proposal", v: { name, spec: { ...spec, name } } });
                  }
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
