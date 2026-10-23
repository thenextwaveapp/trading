import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { useMyBots } from "../db/queries";
import type { DbBot } from "../db/types";
import { DIRLBL, identicon, pct } from "../lib/format";
import { STAGES, resumePath } from "./build/stages";
import p from "./pages.module.css";
import r from "./build/build.module.css";

export default function Roster() {
  const nav = useNavigate();
  const { user, profile } = useAuth();
  const { data: bots, loading } = useMyBots(user?.id ?? null);

  const byStage = useMemo(() => {
    const m = new Map<string, DbBot[]>(STAGES.map((s) => [s.key, []]));
    for (const b of bots ?? []) (m.get(b.stage) ?? m.get("draft")!).push(b);
    return m;
  }, [bots]);

  const total = bots?.length ?? 0;
  const deployed = byStage.get("deployed")?.length ?? 0;
  const inGym = total - deployed - (byStage.get("draft")?.length ?? 0);

  const open = (b: DbBot) => nav(resumePath(b.stage, b.name));

  return (
    <>
      <div className={p.top}>
        <div>
          <h1 className={p.title}>Your roster</h1>
          <div className={p.subtitle}>
            {profile?.handle ? `@${profile.handle} · ` : ""}the bots you've made, by where they are.
          </div>
        </div>
        <button className={`${p.btn} ${p.pri}`} onClick={() => nav("/build/compose?start=describe")}>
          Build a bot
        </button>
      </div>

      <div className={p.body}>
        {loading ? (
          <div className="muted" style={{ padding: 40 }}>Loading your roster…</div>
        ) : total === 0 ? (
          <EmptyRoster onBuild={() => nav("/build/compose?start=describe")} />
        ) : (
          <>
            <section className={p.statgrid} style={{ gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", marginBottom: 32 }}>
              <Stat label="Bots" value={String(total)} />
              <Stat label="In the gym" value={String(inGym)} sub="training → ready" />
              <Stat label="Deployed" value={String(deployed)} sub="battling now" />
            </section>

            <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
              {STAGES.map((s) => {
                const items = byStage.get(s.key) ?? [];
                if (items.length === 0) return null;
                return (
                  <div key={s.key}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 12 }}>
                      <h2 className={p.h2}>{s.label}</h2>
                      <span className="num muted">{items.length}</span>
                      <span className="lbl">{s.blurb}</span>
                    </div>
                    <div className={r.kanban} style={{ gridTemplateColumns: "repeat(auto-fill,minmax(220px,1fr))", display: "grid", gap: 12 }}>
                      {items.map((b) => (
                        <div key={b.id} className={r.kcard} style={{ cursor: "pointer" }} onClick={() => open(b)}>
                          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            <svg width="34" height="34" viewBox="0 0 34 34"><rect width="34" height="34" rx="9" fill="#12161D" /><path d={identicon(b.name, 22)} fill={b.builder?.avatar_color || "#3a81d7"} transform="translate(6 6)" /></svg>
                            <div style={{ minWidth: 0 }}>
                              <div className={r.kName}>{b.name}</div>
                              <div className="lbl">{DIRLBL[b.direction ?? ""] ?? b.direction ?? "—"}</div>
                            </div>
                          </div>
                          {b.bt != null && (
                            <div className="num lbl" style={{ marginTop: 10 }}>{pct(b.bt, true)}/trade backtest</div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </>
  );
}

function EmptyRoster({ onBuild }: { onBuild: () => void }) {
  return (
    <section style={{ maxWidth: 520, padding: "48px 0" }}>
      <h2 style={{ fontSize: 26, fontWeight: 600, letterSpacing: "-0.02em" }}>Your roster is empty.</h2>
      <p className={p.subtitle} style={{ marginTop: 10, lineHeight: 1.6 }}>
        Build your first bot — name it, pick a family, tune it — then send it through the gym:
        training, the honesty trials, the weather gate. The ones that earn it get deployed to your fleet.
      </p>
      <button className={`${p.btn} ${p.pri}`} style={{ marginTop: 20, height: 46 }} onClick={onBuild}>
        Build your first bot →
      </button>
    </section>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className={p.statcell}>
      <div className="lbl">{label}</div>
      <div className={`num ${p.statBig}`}>{value}</div>
      {sub && <div className="lbl" style={{ marginTop: 4 }}>{sub}</div>}
    </div>
  );
}
