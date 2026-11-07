import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { fetchCandles } from "../api/client";
import { useAuth } from "../auth";
import { supabase } from "../db/supabase";
import { entitlementOf } from "../lib/billing";
import { useUpgrade } from "../components/UpgradeModal";

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

export interface ConvoMeta {
  id: string;
  title: string;
  ts: string;
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
  /** chat history: past conversations, open one, start fresh, delete one */
  conversations: ConvoMeta[];
  openConversation: (id: string) => Promise<void>;
  newChat: () => void;
  deleteConversation: (id: string) => void;
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
// Free users get a small taste of the co-pilot, then it's a Pro feature.
const AI_USED_KEY = "pf_ai_used";
const FREE_AI_QUOTA = 5;

export function AssistantProvider({ children }: { children: ReactNode }) {
  const loc = useLocation();
  const { user, subscription } = useAuth();
  const upgrade = useUpgrade();
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

  // History lives in pf_assistant_messages (RLS: owner only), grouped into
  // conversations. On sign-in: resume the latest conversation and build the
  // history list. Signed-out chats stay ephemeral.
  const convId = useRef<string>(crypto.randomUUID());
  const [conversations, setConversations] = useState<ConvoMeta[]>([]);
  const mapRow = (r: { role: string; content: string; proposal: unknown }): ChatMsg => ({
    role: r.role as ChatMsg["role"],
    content: r.content,
    proposal: (r.proposal as Proposal | null) ?? undefined,
  });

  useEffect(() => {
    if (!user) {
      setMessages([]);
      setConversations([]);
      return;
    }
    let dead = false;
    void supabase
      .from("pf_assistant_messages")
      .select("conversation_id,role,content,proposal,created_at")
      .order("created_at", { ascending: true })
      .limit(400)
      .then(({ data }) => {
        if (dead || !data) return;
        const groups = new Map<string, typeof data>();
        for (const r of data) {
          const k = (r.conversation_id as string | null) ?? "legacy";
          if (!groups.has(k)) groups.set(k, []);
          groups.get(k)!.push(r);
        }
        const metas = [...groups.entries()]
          .map(([id, rows]) => ({
            id,
            title: (rows.find((r) => r.role === "user")?.content ?? "Conversation").slice(0, 64),
            ts: rows[rows.length - 1].created_at as string,
            rows,
          }))
          .sort((a, b) => (a.ts < b.ts ? 1 : -1));
        setConversations(metas.map(({ id, title, ts }) => ({ id, title, ts })));
        const latest = metas[0];
        if (latest) {
          convId.current = latest.id === "legacy" ? crypto.randomUUID() : latest.id;
          setMessages(latest.rows.map(mapRow));
        }
      });
    return () => {
      dead = true;
    };
  }, [user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // fire-and-forget persistence — a history hiccup never blocks the chat
  const persist = useCallback(
    (msg: ChatMsg) => {
      if (!user) return;
      const id = convId.current;
      // NB: supabase builders are lazy — nothing fires until .then() is called
      void supabase
        .from("pf_assistant_messages")
        .insert({
          user_id: user.id,
          conversation_id: id,
          role: msg.role,
          content: msg.content,
          proposal: msg.proposal ?? null,
        })
        .then(({ error }) => {
          if (error) console.warn("assistant history save failed:", error.message);
        });
      // a conversation exists in the list from its first user message
      if (msg.role === "user") {
        setConversations((cs) =>
          cs.some((c) => c.id === id)
            ? cs
            : [{ id, title: msg.content.slice(0, 64), ts: new Date().toISOString() }, ...cs],
        );
      }
    },
    [user],
  );

  const openConversation = useCallback(async (id: string) => {
    let q = supabase
      .from("pf_assistant_messages")
      .select("role,content,proposal")
      .order("created_at", { ascending: true });
    q = id === "legacy" ? q.is("conversation_id", null) : q.eq("conversation_id", id);
    const { data } = await q;
    convId.current = id === "legacy" ? crypto.randomUUID() : id;
    setMessages((data ?? []).map(mapRow));
  }, []);

  const newChat = useCallback(() => {
    convId.current = crypto.randomUUID();
    setMessages([]);
  }, []);

  const deleteConversation = useCallback(
    (id: string) => {
      if (user) {
        let q = supabase.from("pf_assistant_messages").delete().eq("user_id", user.id);
        q = id === "legacy" ? q.is("conversation_id", null) : q.eq("conversation_id", id);
        void q.then(({ error }) => {
          if (error) console.warn("assistant history delete failed:", error.message);
        });
      }
      setConversations((cs) => cs.filter((c) => c.id !== id));
      if (convId.current === id) {
        convId.current = crypto.randomUUID();
        setMessages([]);
      }
    },
    [user],
  );

  const clear = useCallback(() => deleteConversation(convId.current), [deleteConversation]);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || busy) return;
      // Pro feature with a small free taste: count free sends, then prompt.
      if (!entitlementOf(subscription).entitled) {
        const used = Number(localStorage.getItem(AI_USED_KEY) ?? "0");
        if (used >= FREE_AI_QUOTA) {
          upgrade.open("The AI co-pilot is a Pro feature.");
          return;
        }
        localStorage.setItem(AI_USED_KEY, String(used + 1));
      }
      const nextHistory: ChatMsg[] = [...messages, { role: "user", content: trimmed }];
      setMessages(nextHistory);
      persist({ role: "user", content: trimmed });
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
        if (acc) persist({ role: "assistant", content: acc, proposal });
      } catch (e) {
        setMessages((m) => [...m, { role: "assistant", content: "Couldn't reach the assistant. Try again." }]);
      } finally {
        setBusy(false);
      }
    },
    [busy, messages, loc.pathname, subscription, upgrade, persist],
  );

  const api = useMemo<AssistantApi>(
    () => ({
      enabled, setEnabled, open, setOpen, messages, busy, send, clear,
      conversations, openConversation, newChat, deleteConversation,
      setPageContext, focusLabel, focusOn,
    }),
    [enabled, setEnabled, open, messages, busy, send, clear,
     conversations, openConversation, newChat, deleteConversation,
     setPageContext, focusLabel, focusOn],
  );

  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}
