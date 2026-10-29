import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAssistant } from "./AssistantProvider";
import s from "./Assistant.module.css";

export default function Assistant() {
  const a = useAssistant();
  const nav = useNavigate();
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [a.messages, a.busy, a.open]);

  if (!a.enabled) return null;

  const submit = () => {
    const t = draft.trim();
    if (!t) return;
    setDraft("");
    void a.send(t);
  };

  const build = (p: { description?: string }) => {
    a.setOpen(false);
    // Do exactly what the manual "Compose your strategy" box does: hand the
    // strategy text to the parser. The token changes every click so Compose
    // re-parses even when it's already mounted.
    if (!p.description) return;
    nav(`/build/compose?prompt=${encodeURIComponent(p.description)}&k=${Date.now()}`);
  };

  if (!a.open) {
    return (
      <button className={s.bubble} onClick={() => a.setOpen(true)} aria-label="Open assistant">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M12 3l1.9 4.6L18.5 9l-4.6 1.9L12 15l-1.9-4.1L5.5 9l4.6-1.4L12 3Z" />
          <path d="M18 14l.9 2.1L21 17l-2.1.9L18 20l-.9-2.1L15 17l2.1-.9L18 14Z" />
        </svg>
      </button>
    );
  }

  return (
    <div className={s.panel}>
      <div className={s.head}>
        <span className={s.title}>
          <span className={s.spark} />Assistant
        </span>
        <div className={s.headBtns}>
          {a.messages.length > 0 && (
            <button className={s.icon} onClick={a.clear} title="Clear">Clear</button>
          )}
          <button className={s.icon} onClick={() => a.setOpen(false)} aria-label="Minimize">✕</button>
        </div>
      </div>

      <div className={s.body} ref={scrollRef}>
        {a.messages.length === 0 && (
          <div className={s.empty}>
            Ask about what you're looking at — “what happened here?” — or “what strategy would catch more of
            these?” I'll ground answers in the real data and can draft a bot you can test.
          </div>
        )}
        {a.messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? s.user : s.asst}>
            <div className={s.msgText}>{m.content}</div>
            {m.proposal && (
              <button className={s.buildBtn} onClick={() => build(m.proposal!)}>
                ⚒ Build “{m.proposal.name}” →
              </button>
            )}
          </div>
        ))}
        {a.busy && <div className={s.asst}><div className={s.dots}><span /><span /><span /></div></div>}
      </div>

      {a.focusLabel && (
        <div className={s.focusChip}>
          <span>📍 Focused on {a.focusLabel}</span>
          <button onClick={() => a.focusOn(null, null)} aria-label="Clear focus">✕</button>
        </div>
      )}
      <div className={s.inputRow}>
        <textarea
          className={s.input}
          rows={1}
          placeholder="Ask the assistant…"
          value={draft}
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
      <div className={s.disclaimer}>Not financial advice. The market is the judge — build it and test on paper.</div>
    </div>
  );
}
