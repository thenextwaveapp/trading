import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../auth";
import { createDraftBot, useBots, useFamilies, useUniverse } from "../../db/queries";
import { DIRLBL } from "../../lib/format";
import p from "../pages.module.css";
import r from "./build.module.css";
import Steps from "./Steps";

export default function Compose() {
  const nav = useNavigate();
  const { user } = useAuth();
  const { data: universe } = useUniverse("fleet-60");
  const { data: families } = useFamilies();
  const { data: bots } = useBots();
  const [name, setName] = useState("New strategy");
  const [famSlug, setFamSlug] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // On family pick, show that family's base definition (its first bot).
  const template = useMemo(() => {
    if (!bots) return null;
    const slug = famSlug ?? families?.[0]?.slug;
    return bots.find((b) => b.family_slug === slug) ?? null;
  }, [bots, famSlug, families]);

  const coins = universe?.pf_universe_coins.map((c) => c.coin_symbol) ?? [];

  // Persist the composed strategy as a draft bot the signed-in user owns,
  // then navigate to `dest`.
  const save = async (dest: string) => {
    if (!user) {
      nav("/signin");
      return;
    }
    setErr(null);
    setSaving(true);
    const { error } = await createDraftBot({
      name: name.trim() || "New strategy",
      owner: user.id,
      family_slug: famSlug ?? families?.[0]?.slug ?? null,
      universe_id: universe?.id ?? null,
      direction: template?.direction ?? null,
      params: template?.params ?? {},
    });
    setSaving(false);
    if (error) {
      setErr(error.message);
      return;
    }
    nav(dest);
  };

  return (
    <>
      <div className={p.crumb}><span className="lk" onClick={() => nav("/build")}>Build</span> / <b>{name}</b></div>
      <Steps current={1} />
      <div className={p.body}>
        <section style={{ display: "flex", flexWrap: "wrap", gap: 32, paddingTop: 28 }}>
          <div style={{ flex: "999 1 520px", minWidth: 0 }}>
            <div style={{ paddingBottom: 28, borderBottom: "1px solid var(--line)" }}>
              <div className={r.label}>Strategy name</div>
              <input value={name} onChange={(e) => setName(e.target.value)} style={{ background: "transparent", border: "none", color: "var(--fg)", fontSize: 36, fontWeight: 500, letterSpacing: "-0.02em", width: "100%", marginTop: 6, outline: "none" }} />
            </div>

            <div className={r.formRow}>
              <h2 className={r.h2}>Market</h2>
              <div className={r.label} style={{ margin: "4px 0 12px" }}>What this bot trades</div>
              <div className={p.seg} style={{ maxWidth: 480 }}>
                {["Crypto", "Stocks · soon", "Predictions · soon"].map((m, i) => (
                  <button key={m} className={`${p.segBtn} ${i === 0 ? p.sel : ""}`} disabled={i > 0}>{m}</button>
                ))}
              </div>
            </div>

            <div className={r.formRow}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <h2 className={r.h2}>Universe</h2>
                <span className="num lbl">{coins.length} coins</span>
              </div>
              <div className={r.label} style={{ margin: "4px 0 12px" }}>{universe?.name ?? "…"} — {universe?.description}</div>
              <div className={r.chipRow}>
                {coins.map((c) => <span key={c} className={r.val}>{c}</span>)}
              </div>
            </div>

            <div className={r.formRow} style={{ borderBottom: "none" }}>
              <h2 className={r.h2}>Start from a strategy family</h2>
              <div className={r.label} style={{ margin: "4px 0 12px" }}>Your tested families — pick one to seed the rules</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {(families ?? []).map((f) => (
                  <button key={f.slug} className={r.blk} style={{ border: famSlug === f.slug ? "1px solid #e9ecf1" : "1px solid transparent", textAlign: "left", cursor: "pointer", width: "100%" }} onClick={() => setFamSlug(f.slug)}>
                    <span className={r.tag}>{f.slug.split("_")[0]}</span>{f.label}
                  </button>
                ))}
              </div>
            </div>

            {template && (
              <div className={r.formRow} style={{ borderBottom: "none" }}>
                <h2 className={r.h2}>Rules <span className="muted" style={{ fontWeight: 400, fontSize: 14 }}>· from {template.name}</span></h2>
                <div className={r.label} style={{ margin: "4px 0 12px" }}>Real parameters of this family's base bot</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <div className={r.blk}><span className={r.tag}>Direction</span>{DIRLBL[template.direction ?? ""] ?? template.direction}</div>
                  {Object.entries(template.params).map(([k, val]) => (
                    <div className={r.blk} key={k}><span className={r.tag}>{k}</span><span className="num" style={{ fontWeight: 400, fontSize: 12 }}>{JSON.stringify(val)}</span></div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div style={{ flex: "1 1 320px", minWidth: 0, display: "flex", flexDirection: "column", gap: 20, paddingTop: 4 }}>
            <div className="card" style={{ padding: 20 }}>
              <div className={r.label}>Universe</div>
              <div className="num" style={{ fontSize: 32, marginTop: 6 }}>{coins.length} coins</div>
              <div className="lbl" style={{ marginTop: 2 }}>{universe?.name}</div>
            </div>
            <button className={`${p.btn} ${p.pri}`} style={{ height: 48, fontSize: 14 }} disabled={saving} onClick={() => save("/build/training")}>
              {saving ? "Saving…" : "Start training"}
            </button>
            <button className={p.btn} style={{ height: 44 }} disabled={saving} onClick={() => save("/build")}>
              {saving ? "Saving…" : user ? "Save draft" : "Sign in to save"}
            </button>
            {err && <div style={{ color: "var(--down, #ff5c6c)", fontSize: 13 }}>{err}</div>}
            {!user && <div className="lbl">Sign in to save this strategy to your fleet.</div>}
          </div>
        </section>
      </div>
    </>
  );
}
