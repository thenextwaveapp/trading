import { botColor } from "../../lib/brand";
import { useMemo, useState, useEffect, type CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../auth";
import { useData } from "../../api/context";
import { deleteBot, useMyBots, useFamilies, useLatestBacktest } from "../../db/queries";
import type { DbBot, Stage } from "../../db/types";
import { DIRLBL, dol, identicon, pct, windowReturn } from "../../lib/format";
import p from "../pages.module.css";
import r from "./build.module.css";
import { STAGES, resumePath } from "./stages";

const PIPELINE = STAGES;
const STAGE_LABEL: Record<string, string> = Object.fromEntries(
  STAGES.map((s) => [s.key, s.label]),
);

const START = [
  ["pump_short", "Fade a pump", "Short the first red bar after a parabolic move."],
  ["capit_long", "Buy a capitulation", "Buy a sharp 24h crash and time the exit."],
  ["momo_long", "Ride momentum", "Buy a high-volume breakout that closes strong."],
];

export default function Hub() {
  const nav = useNavigate();
  const { user } = useAuth();
  const live = useData();
  const { data: rawBots, loading } = useMyBots(user?.id ?? null);
  const { data: families } = useFamilies();
  const [deletedIds, setDeletedIds] = useState<Set<string>>(new Set());
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [cardOrder, setCardOrder] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem("hub_card_order");
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  });
  const [dragId, setDragId] = useState<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);

  const bots = useMemo(
    () => (rawBots ? rawBots.filter((b) => !deletedIds.has(b.id)) : null),
    [rawBots, deletedIds],
  );

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirmId !== id) {
      setConfirmId(id);
      return;
    }
    setDeletingId(id);
    const { error } = await deleteBot(id);
    setDeletingId(null);
    if (!error) {
      setDeletedIds((prev) => new Set(prev).add(id));
      setConfirmId(null);
    }
  };

  const famLabel = useMemo(
    () => new Map((families ?? []).map((f) => [f.slug, f.label])),
    [families],
  );
  const byName = useMemo(() => new Map(live.variants.map((v) => [v.name, v])), [live.variants]);

  // Live return per bot, from the engine's equity curve (joined by name).
  const liveRet = (b: DbBot): number | null => {
    const v = byName.get(b.name);
    return v ? windowReturn(v.curve, null, live.now) : null;
  };

  // Group bots into pipeline columns by stage.
  const columns = useMemo(() => {
    const orderIdx = new Map(cardOrder.map((id, i) => [id, i]));
    const m = new Map<Stage, DbBot[]>(PIPELINE.map((s) => [s.key, []]));
    for (const b of bots ?? []) {
      (m.get(b.stage) ?? m.get("draft")!).push(b);
    }
    for (const [stg, arr] of m.entries()) {
      arr.sort((a, b) => {
        const ia = orderIdx.get(a.id);
        const ib = orderIdx.get(b.id);
        if (ia != null && ib != null) return ia - ib;
        if (ia != null) return -1;
        if (ib != null) return 1;
        if (stg === "deployed") return (liveRet(b) ?? -1e9) - (liveRet(a) ?? -1e9);
        return 0;
      });
    }
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bots, live.variants, live.now, cardOrder]);

  const reorderHubCard = (stage: Stage, fromId: string, toId: string) => {
    if (fromId === toId) return;
    const stageIds = (columns.get(stage) ?? []).map((b) => b.id);
    const fromIdx = stageIds.indexOf(fromId);
    const toIdx = stageIds.indexOf(toId);
    if (fromIdx < 0 || toIdx < 0) return;
    const nextStage = [...stageIds];
    const [moved] = nextStage.splice(fromIdx, 1);
    nextStage.splice(toIdx, 0, moved);
    const otherIds = cardOrder.filter((id) => !stageIds.includes(id));
    const next = [...otherIds, ...nextStage];
    setCardOrder(next);
    try {
      localStorage.setItem("hub_card_order", JSON.stringify(next));
    } catch {
      /* ignore */
    }
  };

  const deployedBots = (bots ?? []).filter((b) => b.stage === "deployed");
  const avgEdge = useMemo(() => {
    const xs = (bots ?? []).map((b) => b.bt).filter((x): x is number => x != null);
    return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
  }, [bots]);
  const best = useMemo(() => {
    let name: string | null = null, top = -Infinity;
    for (const v of live.variants) {
      const ret = windowReturn(v.curve, null, live.now);
      if (ret > top) { top = ret; name = v.name; }
    }
    return name ? { name, ret: top } : null;
  }, [live.variants, live.now]);
  const paperEquity = useMemo(
    () => live.variants.reduce((a, v) => a + (v.equity ?? 0), 0),
    [live.variants],
  );

  // Every bot, best live return first.
  const reports = (bots ?? [])
    .map((b) => ({ b, ret: liveRet(b) }))
    .sort((a, b) => (b.ret ?? -1e9) - (a.ret ?? -1e9));

  const openReport = (name: string) => nav("/build/report/" + encodeURIComponent(name));

  return (
    <>
      <div className={p.top}>
        <div>
          <h1 className={p.title}>Build</h1>
          <div className={p.subtitle}>Compose, train and deploy bots.</div>
        </div>
        <button className={`${p.btn} ${p.pri}`} onClick={() => nav("/build/compose")}>
          New bot
        </button>
      </div>

      <div className={p.body}>
        {loading ? (
          <div className="muted" style={{ padding: 40 }}>Loading your bots…</div>
        ) : (bots ?? []).length === 0 ? (
          <EmptyBuild onStart={(family) => nav(family ? `/build/compose?family=${family}` : "/build/compose")} />
        ) : (
        <>
        <section className={p.statgrid} style={{ gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))", marginBottom: 32 }}>
          <Stat label="Deployed bots" value={String(deployedBots.length)} sub={`${(bots ?? []).length} total`} />
          <Stat label="Avg backtest edge" value={pct(avgEdge, true)} cls={(avgEdge ?? 0) >= 0 ? "up" : "down"} sub="net per trade" />
          <Stat
            label="Best live"
            value={best ? pct(best.ret, true) : "–"}
            cls={(best?.ret ?? 0) >= 0 ? "up" : "down"}
            sub={best?.name ?? ""}
            onClick={best ? () => openReport(best.name) : undefined}
          />
          <Stat label="Paper equity" value={dol(paperEquity)} sub="across the fleet" />
        </section>

        {/* roster, grouped by stage */}
        <div className={p.sectionHead} style={{ marginBottom: 18 }}>
          <div>
            <h2 className={p.h2}>Your bots</h2>
            <div className="lbl" style={{ marginTop: 4 }}>Every bot you've made, by where it is.</div>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 28, marginBottom: 44 }}>
          {STAGES.map((s) => {
            const items = columns.get(s.key) ?? [];
            if (items.length === 0) return null;
            return (
              <div key={s.key}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 12 }}>
                  <h2 className={p.h2}>{s.label}</h2>
                  <span className="num muted">{items.length}</span>
                  <span className="lbl">{s.blurb}</span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(220px,1fr))", gap: 12 }}>
                  {items.map((b) => (
                    <div
                      key={b.id}
                      className={`${r.kcard} ${["training", "trials", "weather"].includes(b.stage) ? "pulseCard" : ""}`}
                      style={{
                        cursor: dragId === b.id ? "grabbing" : "grab",
                        opacity: dragId === b.id ? 0.45 : 1,
                        borderColor: dragOverId === b.id && dragId !== b.id ? "var(--trade)" : undefined,
                      }}
                      draggable
                      onDragStart={(e) => {
                        setDragId(b.id);
                        e.dataTransfer.effectAllowed = "move";
                        e.dataTransfer.setData("text/plain", b.id);
                      }}
                      onDragOver={(e) => {
                        e.preventDefault();
                        e.dataTransfer.dropEffect = "move";
                        if (dragOverId !== b.id) setDragOverId(b.id);
                      }}
                      onDrop={(e) => {
                        e.preventDefault();
                        const src = dragId || e.dataTransfer.getData("text/plain");
                        if (src) reorderHubCard(s.key, src, b.id);
                        setDragId(null);
                        setDragOverId(null);
                      }}
                      onDragEnd={() => {
                        setDragId(null);
                        setDragOverId(null);
                      }}
                      onClick={() => nav(resumePath(b.stage, b.id, b.name))}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <svg width="34" height="34" viewBox="0 0 34 34" style={{ flex: "none" }}><rect width="34" height="34" rx="9" fill="#12161D" /><path d={identicon(b.name, 22)} fill={botColor(b)} transform="translate(6 6)" /></svg>
                        <div style={{ minWidth: 0, flex: 1 }}>
                          <div className={r.kName}>{b.name}</div>
                          <div className="lbl">{DIRLBL[b.direction ?? ""] ?? b.direction ?? "—"}</div>
                        </div>
                        <button
                          type="button"
                          title={confirmId === b.id ? "Click again to permanently delete" : "Delete bot"}
                          disabled={deletingId === b.id}
                          onClick={(e) => void handleDelete(b.id, e)}
                          style={{
                            background: "transparent",
                            border: confirmId === b.id ? "1px solid rgba(255, 92, 108, 0.5)" : "none",
                            borderRadius: 6,
                            color: confirmId === b.id ? "#FF5C6C" : "var(--muted-2)",
                            fontSize: 11,
                            padding: confirmId === b.id ? "2px 6px" : "2px 4px",
                            cursor: "pointer",
                            flex: "none",
                          }}
                        >
                          {deletingId === b.id ? "…" : confirmId === b.id ? "Delete?" : "✕"}
                        </button>
                      </div>
                      {b.bt != null && (
                        <div className="num lbl" style={{ marginTop: 10 }}>{pct(b.bt, true)}/trade backtest</div>
                      )}
                      {b.created_at && (
                        <div className="lbl" style={{ marginTop: 6 }}>created {timeAgo(b.created_at)}</div>
                      )}
                      {b.stage === "training" && <TrainingElapsed botId={b.id} />}
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        <section style={{ display: "flex", flexWrap: "wrap", gap: 24 }}>
          <div style={{ flex: "999 1 560px", minWidth: 0 }}>
            <div className={p.sectionHead}>
              <div>
                <h2 className={p.h2}>Reports <span className="num muted" style={{ fontSize: 14, fontWeight: 400 }}>{reports.length}</span></h2>
                <div className="lbl" style={{ marginTop: 4 }}>Every bot you've tested, with its backtest and live result.</div>
              </div>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ borderCollapse: "collapse", width: "100%" }}>
                <thead><tr>{["Bot", "Family", "Direction", "Stage", "Backtest", "Live", ""].map((h, i) => (
                  <th key={i} style={{ fontWeight: 400, color: "var(--muted-2)", fontSize: 12, textAlign: i >= 4 && i <= 5 ? "right" : "left", padding: "0 14px 12px", whiteSpace: "nowrap" }}>{h}</th>
                ))}</tr></thead>
                <tbody>
                  {reports.map(({ b, ret }) => (
                    <tr key={b.id} style={{ cursor: "pointer" }} onClick={() => openReport(b.name)}>
                      <td style={td("left")}><span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}><span style={{ width: 8, height: 8, borderRadius: "50%", background: botColor(b), flex: "none" }} /><span className="lk">{b.name}</span></span></td>
                      <td style={td("left", "muted")}>{famLabel.get(b.family_slug ?? "")?.split("—")[0].trim() ?? b.family_slug ?? "–"}</td>
                      <td style={td("left", "muted")}>{DIRLBL[b.direction ?? ""] ?? b.direction ?? "–"}</td>
                      <td style={td("left")}><span className={stageCls(b.stage)}>{STAGE_LABEL[b.stage] ?? b.stage}</span></td>
                      <td className={`num ${(b.bt ?? 0) >= 0 ? "up" : "down"}`} style={td("right")}>{b.bt == null ? "–" : pct(b.bt, true)}</td>
                      <td className={`num ${(ret ?? 0) >= 0 ? "up" : "down"}`} style={td("right")}>{ret == null ? "–" : pct(ret, true)}</td>
                      <td style={td("right")}>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 12 }}>
                          <span className="lk lbl">Report ›</span>
                          <button
                            type="button"
                            disabled={deletingId === b.id}
                            onClick={(e) => void handleDelete(b.id, e)}
                            style={{
                              background: "transparent",
                              border: confirmId === b.id ? "1px solid rgba(255, 92, 108, 0.5)" : "none",
                              borderRadius: 6,
                              color: confirmId === b.id ? "#FF5C6C" : "var(--muted-2)",
                              fontSize: 11,
                              padding: confirmId === b.id ? "2px 6px" : "2px 4px",
                              cursor: "pointer",
                            }}
                          >
                            {deletingId === b.id ? "…" : confirmId === b.id ? "Confirm" : "Delete"}
                          </button>
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div style={{ flex: "1 1 300px", display: "flex", flexDirection: "column", gap: 12 }}>
            <div className={p.sectionHead} style={{ margin: "0 0 4px" }}><h2 className={p.h2}>Start a new bot</h2></div>
            {START.map(([mode, t, d]) => (
              <div key={mode} className="card" style={{ padding: 18, display: "flex", gap: 14, alignItems: "center", cursor: "pointer" }} onClick={() => nav("/build/compose?family=" + mode)}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 500 }}>{t}</div>
                  <div className="lbl" style={{ marginTop: 4, lineHeight: 1.5 }}>{d}</div>
                </div>
                <span className="muted">›</span>
              </div>
            ))}
          </div>
        </section>
        </>
        )}
      </div>
    </>
  );
}

function EmptyBuild({ onStart }: { onStart: (family?: string) => void }) {
  return (
    <section style={{ maxWidth: 560, padding: "48px 0" }}>
      <h2 style={{ fontSize: 26, fontWeight: 600, letterSpacing: "-0.02em" }}>You haven't built a bot yet.</h2>
      <p className={p.subtitle} style={{ marginTop: 10, lineHeight: 1.6 }}>
        Compose a strategy, send it through training, the stress tests, the weather gate —
        and track every one you test right here. Your pipeline and reports fill in as you go.
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 16 }}>
        {START.map(([mode, t, d]) => (
          <div key={mode} className="card" style={{ padding: 18, flex: "1 1 220px", minWidth: 0, cursor: "pointer" }} onClick={() => onStart(mode)}>
            <div style={{ fontSize: 14, fontWeight: 500 }}>{t}</div>
            <div className="lbl" style={{ marginTop: 4, lineHeight: 1.5 }}>{d}</div>
          </div>
        ))}
      </div>
      <button className={`${p.btn} ${p.pri}`} style={{ marginTop: 20, height: 46 }} onClick={() => onStart()}>
        Build your first bot →
      </button>
    </section>
  );
}

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const m = Math.floor(ms / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function TrainingElapsed({ botId }: { botId: string }) {
  const { data: bt } = useLatestBacktest(botId);
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!bt || (bt.status !== "pending" && bt.status !== "running")) return;
    const start = new Date(bt.created_at).getTime();
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(t);
  }, [bt?.created_at, bt?.status]);
  if (!bt || (bt.status !== "pending" && bt.status !== "running")) return null;
  const mm = Math.floor(elapsed / 60);
  const ss = elapsed % 60;
  return (
    <div className="lbl" style={{ marginTop: 4, color: "var(--trade)" }}>
      {bt.status === "pending" ? "queued" : "training"} {mm}:{String(ss).padStart(2, "0")}
    </div>
  );
}

function stageCls(stage: string): string {
  if (stage === "deployed") return "up";
  return "";
}

function Stat({ label, value, cls, sub, onClick }: { label: string; value: string; cls?: string; sub?: string; onClick?: () => void }) {
  return (
    <div className={p.statcell} style={onClick ? { cursor: "pointer" } : undefined} onClick={onClick}>
      <div className="lbl">{label}</div>
      <div className={`num ${cls ?? ""} ${p.statBig}`}>{value}</div>
      <div className="lbl" style={{ marginTop: 4 }}>{sub}</div>
    </div>
  );
}

function td(align: "left" | "right", extra?: string): CSSProperties {
  return { padding: "13px 14px", borderTop: "1px solid var(--line)", textAlign: align, whiteSpace: "nowrap", fontSize: 13, color: extra === "muted" ? "var(--muted)" : undefined };
}
