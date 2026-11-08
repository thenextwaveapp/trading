import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { History, Maximize2, Minimize2, PanelLeftClose, PanelLeftOpen, Sparkle, SquarePen, X } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAssistant } from "./AssistantProvider";
import Markdown from "./Markdown";
import s from "./Assistant.module.css";

// one spring drives the grow/shrink between the docked panel and the full-screen
// sheet — both share layoutId="sn-panel", so framer-motion morphs one into the
// other (position + size) instead of unmount/remount flicker.
const PANEL_SPRING = { type: "spring", duration: 0.5, bounce: 0 } as const;

function histDate(iso: string): string {
  const d = new Date(iso);
  const days = (Date.now() - d.getTime()) / 86_400_000;
  if (days < 1) return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

export default function Assistant() {
  const a = useAssistant();
  const nav = useNavigate();
  const loc = useLocation();
  // Compose is where Strategy Navigator does its headline work — building a bot —
  // so the composer wears an animated outline there to invite you in.
  const onBuild = loc.pathname.startsWith("/build/compose");
  const [draft, setDraft] = useState("");
  const [view, setView] = useState<"chat" | "history">("chat");
  const [full, setFull] = useState(false);
  const [rail, setRail] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const dockRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [a.messages, a.busy, a.open, full]);

  // Esc steps back: full screen → docked → collapsed. Click-away collapses,
  // but only when docked (the full-screen sheet has its own backdrop).
  useEffect(() => {
    if (!a.open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (full) setFull(false);
      else a.setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    if (full) return () => document.removeEventListener("keydown", onKey);
    const onDown = (e: MouseEvent) => {
      if (dockRef.current && !dockRef.current.contains(e.target as Node)) a.setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [a.open, full, a]);

  if (!a.enabled) return null;

  const submit = () => {
    const t = draft.trim();
    if (!t) return;
    setDraft("");
    a.setOpen(true);
    void a.send(t);
  };

  const build = (p: { spec?: Record<string, unknown> }) => {
    // Leave full screen so the page is visible, but keep the composer dock open
    // so you can keep iterating: type, Build, watch Compose rebuild, repeat.
    setFull(false);
    // Hand Compose the exact spec the assistant already built, via router state —
    // not a prompt to re-parse. The spec lands verbatim, no second model call and
    // no sampling drift, so clicking Build twice yields the same bot every time.
    if (!p.spec) return;
    nav("/build/compose", { state: { assistantSpec: p.spec } });
  };

  // ---- shared pieces, so docked + full-screen render identically ----
  const messages = (
    <>
      {a.messages.length === 0 && (
        <div className={s.empty}>
          Ask about what you're looking at — “what happened here?” — or “what strategy would catch more of
          these?” I'll ground answers in the real data and can draft a bot you can test.
        </div>
      )}
      {a.messages.map((m, i) => (
        <div key={i} className={m.role === "user" ? s.user : s.asst}>
          <div className={s.msgText}>
            {m.role === "assistant" ? <Markdown>{m.content}</Markdown> : m.content}
          </div>
          {m.proposal?.spec && (
            <button className={s.buildBtn} onClick={() => build(m.proposal!)}>
              ⚒ Build “{m.proposal.name}” →
            </button>
          )}
        </div>
      ))}
      {a.busy && <div className={s.asst}><div className={s.dots}><span /><span /><span /></div></div>}
    </>
  );

  // the one Strategy Navigator bar — identical whether docked or floating in
  // full screen; only the container around it changes
  const composer = (
    <div className={`${s.bar} ${onBuild ? s.barBuild : ""}`}>
      <Sparkle className={s.barSpark} size={18} strokeWidth={1.8} />
      <textarea
        className={s.input}
        rows={1}
        placeholder="Ask the Strategy Navigator…"
        value={draft}
        onFocus={() => a.setOpen(true)}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
      />
      <button className={s.send} onClick={submit} disabled={a.busy || !draft.trim()} aria-label="Send">
        ↑
      </button>
    </div>
  );

  const focusChip = a.focusLabel && (
    <div className={s.focusChip}>
      <span>📍 Focused on {a.focusLabel}</span>
      <button onClick={() => a.focusOn(null, null)} aria-label="Clear focus">✕</button>
    </div>
  );

  const historyRows = (
    a.conversations.length === 0 ? (
      <div className={s.empty}>No past chats yet.</div>
    ) : (
      a.conversations.map((c) => (
        <div key={c.id} className={s.histRow}>
          <button
            className={s.histMain}
            onClick={() => { void a.openConversation(c.id); setView("chat"); }}
          >
            <span className={s.histTitle}>{c.title}</span>
            <span className={s.histTs}>{histDate(c.ts)}</span>
          </button>
          <button className={s.histDel} onClick={() => a.deleteConversation(c.id)} aria-label="Delete chat" title="Delete">
            <X size={13} strokeWidth={1.6} />
          </button>
        </div>
      ))
    )
  );

  const open = a.open;

  // One tree. The dock (with the single, persistent composer) is always
  // rendered; full screen layers a sheet BEHIND the bar, so the Strategy
  // Navigator bar is the exact same element in both modes — never remounts.
  return (
    <>
      {/* backdrop: blurred page behind the sheet, fades in/out on its own */}
      <AnimatePresence>
        {full && open && (
          <motion.div
            key="sn-backdrop"
            className={s.fullWrap}
            onMouseDown={() => setFull(false)}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
          />
        )}
      </AnimatePresence>

      {/* full-screen sheet — messages + history sidebar, but NOT the composer
          (that stays the floating dock bar). Shares layoutId with the docked
          panel, so it grows out of / shrinks back into the dock. */}
      {full && open && (
        <div className={s.sheetCage}>
          <motion.div
            layoutId="sn-panel"
            transition={PANEL_SPRING}
            className={`${s.sheet} ${rail ? "" : s.sheetNoRail}`}
          >
            <aside className={s.side}>
              <div className={s.sideInner}>
                <div className={s.sideHead}>
                  <span className={s.title}>
                    <Sparkle className={s.spark} size={15} strokeWidth={1.8} />
                    Strategy Navigator
                  </span>
                </div>
                <button className={s.newChat} onClick={() => { a.newChat(); setView("chat"); }}>
                  <SquarePen size={15} strokeWidth={1.5} />
                  New chat
                </button>
                <div className={s.sideLabel}>History</div>
                <div className={s.sideList}>{historyRows}</div>
              </div>
            </aside>

            <main className={s.main}>
              <div className={s.mainHead}>
                <button
                  className={s.icon}
                  onClick={() => setRail((r) => !r)}
                  title={rail ? "Collapse sidebar" : "Expand sidebar"}
                  aria-label={rail ? "Collapse sidebar" : "Expand sidebar"}
                >
                  {rail ? <PanelLeftClose size={16} strokeWidth={1.5} /> : <PanelLeftOpen size={16} strokeWidth={1.5} />}
                </button>
                <button className={s.icon} onClick={() => setFull(false)} title="Exit full screen" aria-label="Exit full screen">
                  <Minimize2 size={16} strokeWidth={1.5} />
                </button>
              </div>
              <div className={s.mainBody} ref={scrollRef}>
                <div className={s.col}>{messages}</div>
              </div>
            </main>
          </motion.div>
        </div>
      )}

      {/* the dock: persistent composer; the docked conversation only when
          NOT full (full screen shows messages in the sheet instead) */}
      <div className={`${s.dock} ${full && open ? s.dockOver : ""}`} ref={dockRef}>
        {open && !full && (
          <motion.div
            layoutId="sn-panel"
            transition={PANEL_SPRING}
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            className={s.conv}
          >
            <div className={s.head}>
              <span className={s.title}>
                <Sparkle className={s.spark} size={15} strokeWidth={1.8} />
                {view === "history" ? "History" : "Strategy Navigator"}
              </span>
              <div className={s.headBtns}>
                <button
                  className={`${s.icon} ${view === "history" ? s.iconOn : ""}`}
                  onClick={() => setView((v) => (v === "history" ? "chat" : "history"))}
                  title="Chat history"
                  aria-label="Chat history"
                >
                  <History size={15} strokeWidth={1.5} />
                </button>
                <button
                  className={s.icon}
                  onClick={() => { a.newChat(); setView("chat"); }}
                  title="New chat"
                  aria-label="New chat"
                >
                  <SquarePen size={15} strokeWidth={1.5} />
                </button>
                <button
                  className={s.icon}
                  onClick={() => setFull(true)}
                  title="Full screen"
                  aria-label="Full screen"
                >
                  <Maximize2 size={15} strokeWidth={1.5} />
                </button>
              </div>
            </div>

            {view === "history" ? (
              <div className={s.body}>{historyRows}</div>
            ) : (
              <div className={s.body} ref={scrollRef}>
                {messages}
                <div className={s.disclaimer}>Not financial advice. The market is the judge — build it and test on paper.</div>
              </div>
            )}
          </motion.div>
        )}

        {focusChip}
        {composer}
      </div>
    </>
  );
}
