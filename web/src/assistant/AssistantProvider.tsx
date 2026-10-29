import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { fetchCandles } from "../api/client";

export interface Proposal {
  name: string;
  spec?: Record<string, unknown>;   // full structured StrategySpec from the assistant
  description?: string;             // one-line fallback (older responses)
}
export interface ChatMsg {
  role: "user" | "assistant";
  content: string;
  proposal?: Proposal | null;
}
/** What a page publishes about what the user is looking at, so the assistant is
 *  grounded in the real chart/market instead of guessing. */
export interface PageContext {
  symbol?: string;
  interval?: string;
  market?: Record<string, unknown>;
  news?: { title: string }[];
  /** A compact, bounded summary of what's visible on the current page —
   *  names, prices, rankings already rendered. Cheap to pass, no pixels. */
  screen?: { title: string; rows: string[] };
}

interface AssistantApi {
  enabled: boolean;
  setEnabled: (v: boolean) => void;
  open: boolean;
  setOpen: (v: boolean) => void;
  messages: ChatMsg[];
  busy: boolean;
  send: (text: string) => Promise<void>;
  clear: () => void;
  setPageContext: (ctx: PageContext | null) => void;
  /** Point the assistant at a specific candle/time (from a chart click). */
  focusLabel: string | null;
  focusOn: (tMs: number | null, label: string | null) => void;
}

const Ctx = createContext<AssistantApi | null>(null);
export const useAssistant = (): AssistantApi => {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAssistant outside provider");
  return v;
};

const KEY = "pf_assistant_enabled";

export function AssistantProvider({ children }: { children: ReactNode }) {
  const loc = useLocation();
  const [enabled, setEnabledState] = useState(() => localStorage.getItem(KEY) !== "false");
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [busy, setBusy] = useState(false);
  const [focusLabel, setFocusLabel] = useState<string | null>(null);
  const focusT = useRef<number | null>(null);
  const pageCtx = useRef<PageContext | null>(null);

  const focusOn = useCallback((tMs: number | null, label: string | null) => {
    focusT.current = tMs;
    setFocusLabel(label);
    if (tMs != null) setOpen(true);
  }, []);

  const setEnabled = useCallback((v: boolean) => {
    localStorage.setItem(KEY, v ? "true" : "false");
    setEnabledState(v);
    if (!v) setOpen(false);
  }, []);

  const setPageContext = useCallback((ctx: PageContext | null) => {
    pageCtx.current = ctx;
  }, []);

  const clear = useCallback(() => setMessages([]), []);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || busy) return;
      const nextHistory: ChatMsg[] = [...messages, { role: "user", content: trimmed }];
      setMessages(nextHistory);
      setBusy(true);
      try {
        const pc = pageCtx.current;
        const context: Record<string, unknown> = { path: loc.pathname };
        if (pc?.screen) {
          context.screen = { title: pc.screen.title, rows: pc.screen.rows.slice(0, 20).map((r) => r.slice(0, 120)) };
        }
        if (pc?.symbol) {
          context.symbol = pc.symbol;
          context.interval = pc.interval ?? "15m";
          if (pc.market) context.market = pc.market;
          if (pc.news) context.news = pc.news;
          try {
            const candles = await fetchCandles({ symbol: pc.symbol, interval: pc.interval ?? "15m", limit: 60 });
            const compact = candles.slice(-60).map((c) => ({ t: c.t, o: c.o, h: c.h, l: c.l, c: c.c }));
            context.candles = compact;
            // Resolve a chart-click focus to the nearest bar in view.
            if (focusT.current != null && compact.length) {
              let best = compact[0];
              for (const c of compact) if (Math.abs(c.t - focusT.current) < Math.abs(best.t - focusT.current)) best = c;
              context.focus = {
                t: best.t,
                iso: new Date(best.t).toISOString(),
                o: best.o, h: best.h, l: best.l, c: best.c,
                barsAgo: compact.length - 1 - compact.indexOf(best),
              };
            }
          } catch {
            /* grounding is best-effort */
          }
        }
        const res = await fetch(`${import.meta.env.VITE_SUPABASE_URL}/functions/v1/assistant`, {
          method: "POST",
          headers: { "content-type": "application/json", apikey: import.meta.env.VITE_SUPABASE_KEY },
          body: JSON.stringify({
            messages: nextHistory.map((m) => ({ role: m.role, content: m.content })),
            context,
          }),
        });
        if (!res.ok || !res.body) {
          const data = await res.json().catch(() => null);
          setMessages((m) => [...m, { role: "assistant", content: `Sorry — ${data?.error ?? "request failed"}` }]);
          return;
        }

        // Stream NDJSON events into a single growing assistant message.
        let acc = "";
        let status = "";
        let proposal: Proposal | null = null;
        const paint = () => {
          setBusy(false);
          const content = acc || (status ? `_${status}_` : "");
          setMessages((m) => {
            const msg: ChatMsg = { role: "assistant", content, proposal };
            // Pure: replace the streaming assistant bubble if it's last, else
            // append. (Must not depend on an external flag — StrictMode invokes
            // updaters twice and an impure one would clobber the user message.)
            if (m.length && m[m.length - 1].role === "assistant") {
              const copy = m.slice();
              copy[copy.length - 1] = msg;
              return copy;
            }
            return [...m, msg];
          });
        };
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split("\n");
          buf = lines.pop() ?? "";
          for (const line of lines) {
            if (!line.trim()) continue;
            let ev: { type: string; v: unknown };
            try {
              ev = JSON.parse(line);
            } catch {
              continue;
            }
            if (ev.type === "text") {
              acc += String(ev.v);
              paint();
            } else if (ev.type === "status") {
              status = String(ev.v);
              if (!acc) paint();
            } else if (ev.type === "proposal") {
              proposal = ev.v as Proposal;
              paint();
            } else if (ev.type === "error" && !acc) {
              acc = "Something interrupted the reply — try again.";
              paint();
            }
          }
        }
        setMessages((m) =>
          m.length && m[m.length - 1].role === "assistant"
            ? m
            : [...m, { role: "assistant", content: acc || "…", proposal }],
        );
      } catch (e) {
        setMessages((m) => [...m, { role: "assistant", content: "Couldn't reach the assistant. Try again." }]);
      } finally {
        setBusy(false);
      }
    },
    [busy, messages, loc.pathname],
  );

  const api = useMemo<AssistantApi>(
    () => ({ enabled, setEnabled, open, setOpen, messages, busy, send, clear, setPageContext, focusLabel, focusOn }),
    [enabled, setEnabled, open, messages, busy, send, clear, setPageContext, focusLabel, focusOn],
  );

  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}
