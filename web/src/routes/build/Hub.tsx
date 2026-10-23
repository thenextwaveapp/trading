import { useMemo, type CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../auth";
import { useData } from "../../api/context";
import { useMyBots, useFamilies } from "../../db/queries";
import type { DbBot, Stage } from "../../db/types";
import { DIRLBL, dol, pct, windowReturn } from "../../lib/format";
import p from "../pages.module.css";
import r from "./build.module.css";
import { STAGES, resumePath } from "./stages";

const PIPELINE = STAGES;
const STAGE_LABEL: Record<string, string> = Object.fromEntries(
  STAGES.map((s) => [s.key, s.label]),
);

const START = [
  ["describe", "Describe it", "Write the strategy in plain language and we'll turn it into rules."],
  ["template", "Use a template", "Start from a proven family — a pump fade, a capitulation buy."],
  ["blank", "Start blank", "Build the entry and exit rules yourself from scratch."],
];

export default function Hub() {
  const nav = useNavigate();
  const { user } = useAuth();
  const live = useData();
  const { data: bots, loading } = useMyBots(user?.id ?? null);
  const { data: families } = useFamilies();

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
    const m = new Map<Stage, DbBot[]>(PIPELINE.map((s) => [s.key, []]));
    for (const b of bots ?? []) {
      (m.get(b.stage) ?? m.get("draft")!).push(b);
    }
    // Within deployed, sort by live return desc so the best sits on top.
    m.get("deployed")?.sort((a, b) => (liveRet(b) ?? -1e9) - (liveRet(a) ?? -1e9));
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bots, live.variants, live.now]);

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
        <button className={`${p.btn} ${p.pri}`} onClick={() => nav("/build/compose?start=describe")}>
          New bot
        </button>
      </div>

      <div className={p.body}>
        {loading ? (
          <div className="muted" style={{ padding: 40 }}>Loading your bots…</div>
        ) : (bots ?? []).length === 0 ? (
          <EmptyBuild onStart={(mode) => nav(`/build/compose?start=${mode}`)} />
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

        {/* pipeline kanban */}
        <div className={p.sectionHead} style={{ marginBottom: 14 }}>
          <div>
            <h2 className={p.h2}>Pipeline</h2>
            <div className="lbl" style={{ marginTop: 4 }}>Every bot, by where it is in the journey.</div>
          </div>
        </div>
        <div className={r.kanban} style={{ marginBottom: 44 }}>
          {PIPELINE.map((s) => {
            const items = columns.get(s.key) ?? [];
            const shown = items.slice(0, 6);
            return (
              <div className={r.col} key={s.key}>
                <div className={r.colHead}>
                  <span>{s.label}</span>
                  <span className="num muted">{items.length}</span>
                </div>
                {shown.map((b) => {
                  const ret = liveRet(b);
                  return (
                    <div
                      key={b.id}
                      className={`${r.kcard} ${s.key === "ready" ? r.ready : ""}`}
                      style={{ cursor: "pointer" }}
                      onClick={() => nav(b.stage === "deployed" ? "/build/report/" + encodeURIComponent(b.name) : resumePath(b.stage, b.name))}
                    >
                      <div className={r.kName}>{b.name}</div>
                      <div className={r.kDesc}>{b.note || famLabel.get(b.family_slug ?? "") || s.blurb}</div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginTop: 10 }}>
                        <span className="num lbl">{b.bt == null ? "" : pct(b.bt, true) + "/trade"}</span>
                        {s.key === "deployed" && ret != null && (
                          <span className={`num ${ret >= 0 ? "up" : "down"}`} style={{ fontSize: 12 }}>{pct(ret, true)}</span>
                        )}
                        {s.key === "ready" && <span className="lk lbl" style={{ color: "#8BB4E8" }}>Deploy →</span>}
                      </div>
                    </div>
                  );
                })}
                {items.length > shown.length && (
                  <div className="lbl" style={{ padding: "2px 2px" }}>+{items.length - shown.length} more</div>
                )}
                {items.length === 0 && (
                  <div
                    className={`${r.kcard} ${r.dashed}`}
                    onClick={() => nav("/build/compose?start=blank&stage=" + s.key)}
                  >
                    + New
                  </div>
                )}
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
                      <td style={td("left")}><span className="lk">{b.name}</span></td>
                      <td style={td("left", "muted")}>{famLabel.get(b.family_slug ?? "")?.split("—")[0].trim() ?? b.family_slug ?? "–"}</td>
                      <td style={td("left", "muted")}>{DIRLBL[b.direction ?? ""] ?? b.direction ?? "–"}</td>
                      <td style={td("left")}><span className={stageCls(b.stage)}>{STAGE_LABEL[b.stage] ?? b.stage}</span></td>
                      <td className={`num ${(b.bt ?? 0) >= 0 ? "up" : "down"}`} style={td("right")}>{b.bt == null ? "–" : pct(b.bt, true)}</td>
                      <td className={`num ${(ret ?? 0) >= 0 ? "up" : "down"}`} style={td("right")}>{ret == null ? "–" : pct(ret, true)}</td>
                      <td style={td("right")}><span className="lk lbl">Report ›</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div style={{ flex: "1 1 300px", display: "flex", flexDirection: "column", gap: 12 }}>
            <div className={p.sectionHead} style={{ margin: "0 0 4px" }}><h2 className={p.h2}>Start a new bot</h2></div>
            {START.map(([mode, t, d]) => (
              <div key={mode} className="card" style={{ padding: 18, display: "flex", gap: 14, alignItems: "center", cursor: "pointer" }} onClick={() => nav(`/build/compose?start=${mode}`)}>
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

function EmptyBuild({ onStart }: { onStart: (mode: string) => void }) {
  return (
    <section style={{ maxWidth: 560, padding: "48px 0" }}>
      <h2 style={{ fontSize: 26, fontWeight: 600, letterSpacing: "-0.02em" }}>You haven't built a bot yet.</h2>
      <p className={p.subtitle} style={{ marginTop: 10, lineHeight: 1.6 }}>
        Compose a strategy, send it through the gym — training, the honesty trials, the weather gate —
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
      <button className={`${p.btn} ${p.pri}`} style={{ marginTop: 20, height: 46 }} onClick={() => onStart("describe")}>
        Build your first bot →
      </button>
    </section>
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
