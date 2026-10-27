import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { createSweep, useMyBot, useSweepData, useUniverses } from "../../db/queries";
import type { DbSweep, DbSweepRun, DbUniverse } from "../../db/types";
import {
  CATALOG,
  SPEC_GROUPS,
  SPEC_PARAMS,
  blockingIssues,
  getPath,
  specParam,
  visibleParam,
} from "../../lib/catalog";
import type { SpecParam } from "../../lib/catalog";
import { dol, pct } from "../../lib/format";
import p from "../pages.module.css";
import r from "./build.module.css";
import { withBot } from "./stages";

type AxisDraft = { path: string; values: unknown[] };

const has = (values: unknown[], value: unknown) =>
  values.some((v) => JSON.stringify(v) === JSON.stringify(value));

function numberValues(raw: string): number[] {
  return raw
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .map(Number)
    .filter(Number.isFinite);
}

function defaultValues(param: SpecParam, spec: Record<string, unknown> | null): unknown[] {
  const current = spec ? getPath(spec, param.key) : undefined;
  if (current !== undefined && current !== null) return [current];
  if (param.kind === "bool") return [false, true];
  if (param.kind === "enum") {
    const first = param.options.find((o) => o.backtest);
    return first ? [first.value] : [];
  }
  return [];
}

function enumOptions(param: SpecParam, universes: DbUniverse[]) {
  if (param.key === "market") {
    return CATALOG.markets.map((m) => ({
      value: m.id,
      label: m.label,
      backtest: true,
      reason: "",
    }));
  }
  if (param.key === "universe") {
    return universes.map((u) => ({
      value: u.slug,
      label: u.name || u.slug,
      backtest: true,
      reason: "",
    }));
  }
  return param.options;
}

function ChipValues({
  values,
  options,
  onChange,
}: {
  values: unknown[];
  options: { value: unknown; label: string; backtest: boolean; reason: string }[];
  onChange: (values: unknown[]) => void;
}) {
  const known = new Set(options.map((o) => o.value));
  const extra = values
    .filter((v) => !known.has(v))
    .map((v) => ({ value: v, label: String(v), backtest: true, reason: "" }));
  return (
    <div className={r.chipRow}>
      {[...options, ...extra].map((o) => {
        const on = has(values, o.value);
        return (
          <button
            key={String(o.value)}
            type="button"
            className={`${r.pill} ${on ? r.sel : ""}`}
            disabled={!o.backtest}
            title={o.reason || undefined}
            style={!o.backtest ? { opacity: 0.4, cursor: "not-allowed" } : undefined}
            onClick={() =>
              onChange(
                on
                  ? values.filter((v) => JSON.stringify(v) !== JSON.stringify(o.value))
                  : [...values, o.value],
              )
            }
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function NumberValues({
  param,
  values,
  onChange,
}: {
  param: SpecParam;
  values: unknown[];
  onChange: (values: unknown[]) => void;
}) {
  const scale = param.percent ? 100 : 1;
  const display = (v: unknown) => String(Number((Number(v) * scale).toFixed(8)));
  const [raw, setRaw] = useState(values.map(display).join(", "));
  return (
    <div>
      <input
        className={r.input}
        value={raw}
        placeholder={param.percent
          ? "0.5, 0.75, 1"
          : param.kind === "int" ? "8, 16, 24" : "1, 2, 3.5"}
        onChange={(e) => {
          setRaw(e.target.value);
          onChange(numberValues(e.target.value).map((v) => v / scale));
        }}
        style={{ width: "100%", maxWidth: 420 }}
      />
      <div className="lbl" style={{ marginTop: 6 }}>
        Comma-separated values{param.percent ? " in percent" : ""}. Each value
        becomes one backtest.
      </div>
    </div>
  );
}

function JsonValues({
  values,
  onChange,
  hint,
}: {
  values: unknown[];
  onChange: (values: unknown[]) => void;
  hint: string;
}) {
  const [raw, setRaw] = useState(() => JSON.stringify(values, null, 2));
  const [bad, setBad] = useState<string | null>(null);
  return (
    <div>
      <textarea
        className={r.input}
        value={raw}
        spellCheck={false}
        onChange={(e) => {
          const text = e.target.value;
          setRaw(text);
          if (!text.trim()) {
            setBad(null);
            onChange([]);
            return;
          }
          try {
            const parsed = JSON.parse(text);
            if (!Array.isArray(parsed)) throw new Error("Expected an array of values");
            setBad(null);
            onChange(parsed);
          } catch (err) {
            setBad(err instanceof Error ? err.message : "Invalid JSON");
            onChange([]);
          }
        }}
        style={{
          width: "100%",
          minHeight: 112,
          padding: "10px 12px",
          fontFamily: "var(--font-mono)",
          fontSize: 12,
          lineHeight: 1.5,
          resize: "vertical",
        }}
      />
      <div className="lbl" style={{ marginTop: 6, color: bad ? "var(--down, #ff5c6c)" : undefined }}>
        {bad || hint}
      </div>
    </div>
  );
}

function AxisValues({
  param,
  values,
  onChange,
  universes,
}: {
  param: SpecParam;
  values: unknown[];
  onChange: (values: unknown[]) => void;
  universes: DbUniverse[];
}) {
  if (param.kind === "bool") {
    return (
      <ChipValues
        values={values}
        options={[
          { value: false, label: "Off", backtest: true, reason: "" },
          { value: true, label: "On", backtest: true, reason: "" },
        ]}
        onChange={onChange}
      />
    );
  }
  if (param.kind === "enum") {
    return (
      <ChipValues
        values={values}
        options={enumOptions(param, universes)}
        onChange={onChange}
      />
    );
  }
  if (param.kind === "int" || param.kind === "float") {
    return <NumberValues param={param} values={values} onChange={onChange} />;
  }
  if (param.kind === "int_list") {
    return (
      <JsonValues
        values={values}
        onChange={onChange}
        hint='One array per variant, e.g. [[], [0,1,2], [13,14,15,16]]. Empty array = all.'
      />
    );
  }
  if (param.kind === "condition") {
    return (
      <JsonValues
        values={values}
        onChange={onChange}
        hint='One condition tree per variant, e.g. [{"logic":"AND","children":[...]}].'
      />
    );
  }
  if (param.key === "universe") {
    if (universes.length) {
      return (
        <ChipValues
          values={values}
          options={enumOptions(param, universes)}
          onChange={onChange}
        />
      );
    }
    return (
      <input
        className={r.input}
        value={values.map(String).join(", ")}
        placeholder="fleet-60, majors"
        onChange={(e) =>
          onChange(
            e.target.value
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean),
          )
        }
        style={{ width: "100%", maxWidth: 420 }}
      />
    );
  }
  return (
    <input
      className={r.input}
      value={values.map(String).join(", ")}
      onChange={(e) =>
        onChange(
          e.target.value
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
        )
      }
      style={{ width: "100%", maxWidth: 420 }}
    />
  );
}

function AxisCard({
  axis,
  param,
  spec,
  universes,
  onChange,
  onRemove,
}: {
  axis: AxisDraft;
  param: SpecParam;
  spec: Record<string, unknown> | null;
  universes: DbUniverse[];
  onChange: (values: unknown[]) => void;
  onRemove: () => void;
}) {
  const active = spec ? visibleParam(param, spec) : false;
  const notes = [
    !active ? "This control is inactive in the current strategy; some values may produce identical runs." : "",
    param.status === "ignored" ? param.reason : "",
    param.status === "partial" ? param.reason : "",
  ].filter(Boolean);
  return (
    <div
      style={{
        border: "1px solid var(--line-2)",
        borderRadius: 12,
        padding: "14px 16px",
        background: "#0b0f14",
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 12 }}>
        <div style={{ flex: 1 }}>
          <div className="lbl">{SPEC_GROUPS.find((g) => g.id === param.group)?.label ?? param.group}</div>
          <div style={{ fontSize: 14, fontWeight: 500, marginTop: 2 }}>{param.label}</div>
          <div className="lbl" style={{ fontFamily: "var(--font-mono)", marginTop: 2 }}>
            {param.key}
          </div>
        </div>
        <button className={p.btn} style={{ height: 28, padding: "0 10px", fontSize: 12 }} onClick={onRemove}>
          Remove
        </button>
      </div>
      <AxisValues
        param={param}
        values={axis.values}
        onChange={onChange}
        universes={universes}
      />
      <div className="lbl" style={{ marginTop: 8 }}>
        {axis.values.length} value{axis.values.length === 1 ? "" : "s"} · {param.help}
      </div>
      {notes.map((n, i) => (
        <div key={i} className="lbl" style={{ marginTop: 6, color: "var(--warn, #d29922)" }}>
          {n}
        </div>
      ))}
    </div>
  );
}

function SweepStatus({ sweep, onRefresh }: { sweep: DbSweep; onRefresh: () => void }) {
  const running = sweep.status === "pending" || sweep.status === "running";
  const failed = sweep.status === "error";
  const label = failed
    ? "The sweep hit an error."
    : sweep.status === "pending"
      ? "Queued — waiting for the engine worker"
      : sweep.status === "running"
        ? "Running the grid…"
        : "Sweep complete";
  return (
    <section className={r.statusCard} style={{ marginTop: 24 }}>
      <span className={running ? r.spin : failed ? "downDot" : "liveDot"} />
      <div>
        <div style={{ fontSize: 15, fontWeight: 500 }}>{label}</div>
        <div className="lbl" style={{ marginTop: 4, lineHeight: 1.5 }}>
          {failed
            ? sweep.error || "The engine could not finish this sweep."
            : sweep.status === "done"
              ? `${sweep.completed_count} result${sweep.completed_count === 1 ? "" : "s"} across ${sweep.run_count} grid point${sweep.run_count === 1 ? "" : "s"}${sweep.window_start && sweep.window_end ? ` · ${sweep.window_start} to ${sweep.window_end}` : ""}`
              : "The worker expands the grid and replays the strategy once per point."}
        </div>
        <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
          <button className={p.btn} onClick={onRefresh}>Refresh</button>
        </div>
      </div>
    </section>
  );
}

function Results({ sweep, runs }: { sweep: DbSweep; runs: DbSweepRun[] }) {
  const sorted = [...runs].sort((a, b) => {
    const av = a.stats?.net_pct_per_trade;
    const bv = b.stats?.net_pct_per_trade;
    if (av == null && bv == null) return a.position - b.position;
    if (av == null) return 1;
    if (bv == null) return -1;
    return bv - av;
  });
  const best = sorted.find((x) => x.stats && !x.error)?.id;
  const errors = runs.filter((x) => x.error).length;
  return (
    <section className="card" style={{ marginTop: 24, padding: "20px 22px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline", flexWrap: "wrap" }}>
        <h2 className={r.h2}>Results</h2>
        <span className="lbl">
          {runs.length} run{runs.length === 1 ? "" : "s"}
          {errors ? ` · ${errors} failed` : ""} · sorted by average trade
        </span>
      </div>
      <div style={{ overflowX: "auto", marginTop: 14 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr className="lbl" style={{ textAlign: "left" }}>
              <th style={{ padding: "8px 10px", fontWeight: 400 }}>Parameters</th>
              <th style={{ padding: "8px 10px", fontWeight: 400 }}>Trades</th>
              <th style={{ padding: "8px 10px", fontWeight: 400 }}>Avg trade</th>
              <th style={{ padding: "8px 10px", fontWeight: 400 }}>Total</th>
              <th style={{ padding: "8px 10px", fontWeight: 400 }}>Win</th>
              <th style={{ padding: "8px 10px", fontWeight: 400 }}>Max DD</th>
              <th style={{ padding: "8px 10px", fontWeight: 400 }}>Final</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((run) => {
              const st = run.stats;
              return (
                <tr
                  key={run.id}
                  style={{
                    borderTop: "1px solid var(--line)",
                    background: run.id === best ? "rgba(61,220,151,.06)" : undefined,
                  }}
                >
                  <td style={{ padding: "10px", fontFamily: "var(--font-mono)", fontSize: 12, minWidth: 220 }}>
                    {run.label}
                    {run.id === best && <span className="lbl" style={{ marginLeft: 8, color: "var(--up)" }}>best</span>}
                    {run.error && (
                      <div style={{ color: "var(--down, #ff5c6c)", fontFamily: "inherit", fontSize: 12, marginTop: 4 }}>
                        {run.error}
                      </div>
                    )}
                  </td>
                  <td className="num" style={{ padding: "10px" }}>{st ? st.n : "—"}</td>
                  <td className={`num ${st && st.net_pct_per_trade >= 0 ? "up" : "down"}`} style={{ padding: "10px" }}>
                    {st ? pct(st.net_pct_per_trade, true) : "—"}
                  </td>
                  <td className={`num ${st && st.total_net_pct >= 0 ? "up" : "down"}`} style={{ padding: "10px" }}>
                    {st ? pct(st.total_net_pct, true) : "—"}
                  </td>
                  <td className="num" style={{ padding: "10px" }}>{st ? Math.round(st.win_rate * 100) + "%" : "—"}</td>
                  <td className="num down" style={{ padding: "10px" }}>
                    {st ? pct(st.max_drawdown * 100) : "—"}
                  </td>
                  <td className="num" style={{ padding: "10px" }}>{st ? dol(st.final_equity) : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="lbl" style={{ marginTop: 10 }}>
        Same tape and costs for every point · {sweep.window_start && sweep.window_end ? `${sweep.window_start} to ${sweep.window_end}` : "shared window"}
      </div>
    </section>
  );
}

export default function Sweep() {
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const botId = sp.get("bot") ?? "";
  const [nonce, setNonce] = useState(0);
  const { data: bot, loading: botLoading } = useMyBot(botId || null, nonce);
  const { loading: sweepLoading, sweep, runs } = useSweepData(bot?.id ?? null, nonce);
  const { data: universes } = useUniverses();
  const [axes, setAxes] = useState<AxisDraft[]>([]);
  const [pendingPath, setPendingPath] = useState("");
  const [creating, setCreating] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setAxes([]);
    setPendingPath("");
    setErr(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bot?.id]);

  useEffect(() => {
    if (!sweep || sweep.status === "done" || sweep.status === "error") return;
    const t = setInterval(() => setNonce((n) => n + 1), 4000);
    return () => clearInterval(t);
  }, [sweep?.status]);

  const spec = (bot?.spec ?? null) as Record<string, unknown> | null;
  const blockers = spec ? blockingIssues(spec, "backtest") : [];
  const axisParams = useMemo(
    () => SPEC_PARAMS.filter((x) => x.sweep && x.backtest),
    [],
  );
  const available = axisParams.filter((x) => !axes.some((a) => a.path === x.key));
  const count = axes.length ? axes.reduce((n, a) => n * a.values.length, 1) : 0;
  const canRun = !!bot && !!spec && axes.length > 0 && count > 0 && blockers.length === 0 && !creating;

  const training = () => nav(withBot("/build/training", bot?.id ?? botId));
  const edit = () => nav(withBot("/build/compose", bot?.id ?? botId));

  const addAxis = () => {
    const param = specParam(pendingPath);
    if (!param) return;
    setAxes((cur) => [...cur, { path: param.key, values: defaultValues(param, spec) }]);
    setPendingPath("");
  };

  const run = async () => {
    setErr(null);
    if (!bot || !spec || !canRun) return;
    setCreating(true);
    const { error } = await createSweep({
      bot_id: bot.id,
      universe_id: bot.universe_id,
      universe_slug: typeof spec.universe === "string" ? spec.universe : "fleet-60",
      spec,
      axes: axes.map((a) => ({ path: a.path, values: a.values })),
    });
    setCreating(false);
    if (error) {
      setErr(error.message);
      return;
    }
    setNonce((n) => n + 1);
  };

  if (botLoading) {
    return (
      <>
        <div className={p.crumb}><b>Build</b> / Sweep</div>
        <div className={p.body} style={{ paddingTop: 28 }}><span className="muted">Loading…</span></div>
      </>
    );
  }
  if (!bot) {
    return (
      <>
        <div className={p.crumb}><b>Build</b> / Sweep</div>
        <div className={p.body} style={{ paddingTop: 28 }}>
          <span className="muted">Pick a bot to sweep. </span>
          <span className="lk" style={{ color: "#8BB4E8" }} onClick={() => nav("/build")}>Back to Build →</span>
        </div>
      </>
    );
  }

  return (
    <>
      <div className={p.crumb}>
        <span className="lk" onClick={() => nav("/build")}>Build</span> /{" "}
        <span className="lk" onClick={training}>{bot.name}</span> / <b>Sweep</b>
      </div>
      <div className={p.body} style={{ paddingTop: 28 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div>
            <h1 style={{ fontSize: 34, letterSpacing: "-0.03em", fontWeight: 500 }}>Parameter sweep</h1>
            <div className="lbl" style={{ marginTop: 6, lineHeight: 1.5 }}>
              Run the same strategy over a grid of parameter values. Every point uses the same tape, costs and window.
            </div>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button className={p.btn} onClick={training}>Back to training</button>
            <button className={p.btn} onClick={edit}>Edit strategy</button>
          </div>
        </div>

        {blockers.length > 0 && (
          <section className={r.statusCard} style={{ marginTop: 24 }}>
            <span className="downDot" />
            <div>
              <div style={{ fontSize: 15, fontWeight: 500 }}>This strategy can't sweep yet.</div>
              <div className="lbl" style={{ marginTop: 4, lineHeight: 1.5 }}>
                Resolve these in Compose first. A sweep uses the same backtest gates as training.
              </div>
              {blockers.map((i) => (
                <div key={i.id} style={{ marginTop: 10, fontSize: 13 }}>
                  <b style={{ color: "var(--down, #ff5c6c)" }}>{i.label}</b>
                  <div className="lbl">{i.reason}</div>
                </div>
              ))}
            </div>
          </section>
        )}

        {!spec && (
          <div className="muted" style={{ marginTop: 24 }}>This bot has no saved strategy spec. Compose it first.</div>
        )}

        {spec && (
          <section className="card" style={{ marginTop: 24, padding: "20px 22px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline", flexWrap: "wrap" }}>
              <h2 className={r.h2}>Grid</h2>
              <span className="lbl">{axes.length} axis{axes.length === 1 ? "" : "es"} · {count} run{count === 1 ? "" : "s"}</span>
            </div>
            <div style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap", marginTop: 14 }}>
              <label style={{ display: "flex", flexDirection: "column", gap: 6, flex: "1 1 300px", maxWidth: 440 }}>
                <span className="lbl">Add parameter</span>
                <select className={r.input} value={pendingPath} onChange={(e) => setPendingPath(e.target.value)}>
                  <option value="">Choose a parameter…</option>
                  {SPEC_GROUPS.map((g) => {
                    const ps = available.filter((x) => x.group === g.id);
                    if (!ps.length) return null;
                    return (
                      <optgroup key={g.id} label={g.label}>
                        {ps.map((x) => (
                          <option key={x.key} value={x.key}>{x.label} — {x.key}{x.status !== "ok" ? ` (${x.status})` : ""}</option>
                        ))}
                      </optgroup>
                    );
                  })}
                </select>
              </label>
              <button className={`${p.btn} ${p.pri}`} onClick={addAxis} disabled={!pendingPath}>
                Add axis
              </button>
            </div>
            <div className="lbl" style={{ marginTop: 8 }}>
              Unsupported by the backtest: {SPEC_PARAMS.filter((x) => !x.backtest).map((x) => x.label).join(", ")}.
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 18 }}>
              {axes.length === 0 && (
                <div className="lbl">No axes yet. Add a parameter to build the grid.</div>
              )}
              {axes.map((axis, i) => {
                const param = specParam(axis.path);
                if (!param) return null;
                return (
                  <AxisCard
                    key={axis.path}
                    axis={axis}
                    param={param}
                    spec={spec}
                    universes={universes ?? []}
                    onChange={(values) =>
                      setAxes((cur) => cur.map((x, j) => (j === i ? { ...x, values } : x)))
                    }
                    onRemove={() => setAxes((cur) => cur.filter((_, j) => j !== i))}
                  />
                );
              })}
            </div>

            <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 18, flexWrap: "wrap" }}>
              <button className={`${p.btn} ${p.pri}`} onClick={run} disabled={!canRun}>
                {creating ? "Queuing…" : count ? `Run ${count} backtest${count === 1 ? "" : "s"}` : "Run sweep"}
              </button>
              {!blockers.length && axes.length > 0 && count === 0 && (
                <span className="lbl">Add at least one value to every axis.</span>
              )}
              {err && <span style={{ color: "var(--down, #ff5c6c)", fontSize: 13 }}>{err}</span>}
            </div>
          </section>
        )}

        {!sweepLoading && sweep && (
          <SweepStatus sweep={sweep} onRefresh={() => setNonce((n) => n + 1)} />
        )}
        {runs.length > 0 && sweep && <Results sweep={sweep} runs={runs} />}
      </div>
    </>
  );
}
