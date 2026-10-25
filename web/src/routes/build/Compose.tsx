import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../auth";
import {
  botNameTaken,
  createBacktest,
  createDraftBot,
  fetchLatestBacktest,
  setBotStage,
  updateDraftBot,
  useMyBot,
  useUniverses,
} from "../../db/queries";
import { CATALOG, indicatorsForMarket, indicatorById } from "../../lib/catalog";
import p from "../pages.module.css";
import r from "./build.module.css";
import { MissingBot, StepLoading } from "./parts";
import Steps from "./Steps";
import { withBot } from "./stages";

// ---- types matching core/expr.py + core/strategy.py ----

type Operand =
  | number
  | { ind: string; params?: Record<string, unknown>; offset?: number };

interface CondNode {
  left: Operand;
  op: string;
  right: Operand;
}

interface CondGroup {
  logic: "AND" | "OR" | "NOT";
  children: AnyNode[];
}

type AnyNode = CondNode | CondGroup;

function isGroup(n: AnyNode): n is CondGroup {
  return !!n && Array.isArray((n as CondGroup).children);
}

interface StopCfg {
  mode: string;
  param?: number;
  window?: number;
  k?: number;
  natr?: number;
  level?: number;
}

interface ExitCfg {
  time_bars: number;
  stop: StopCfg;
  take_profit?: number;
  tp_close?: boolean;
  limit?: number;
  trailing?: { k: number; natr: number };
  exit_conditions?: CondGroup;
}

interface SizingCfg {
  risk: number;
  notional_cap: number;
  weight: number;
}

interface FilterCfg {
  kind: string;
  threshold?: number;
  only?: string[];
  btc_bear?: boolean;
}

interface StrategySpec {
  name: string;
  side: "long" | "short" | "both";
  market: string;
  universe: string;
  fresh: boolean;
  entry: CondGroup;
  exit: ExitCfg;
  sizing: SizingCfg;
  filters: FilterCfg[];
}

const OPS = [
  { v: "ge", l: "≥" },
  { v: "gt", l: ">" },
  { v: "le", l: "≤" },
  { v: "lt", l: "<" },
  { v: "eq", l: "=" },
  { v: "crosses_above", l: "crosses above" },
  { v: "crosses_below", l: "crosses below" },
];

const STOP_MODES = [
  { v: "none", l: "None (time only)" },
  { v: "hh", l: "4h signal high" },
  { v: "dstop", l: "Disaster stop" },
  { v: "sig", l: "Signal-window stop" },
  { v: "trail", l: "Trailing stop" },
];

const LOGICS = ["AND", "OR", "NOT"] as const;

function defaultOperand(): Operand {
  return { ind: "ROC", params: { period: 16 }, offset: 0 };
}

function defaultSpec(universe: string): StrategySpec {
  return {
    name: "",
    side: "short",
    market: "crypto_perp",
    universe,
    fresh: false,
    entry: { logic: "AND", children: [] },
    exit: { time_bars: 16, stop: { mode: "hh", param: 0.0, window: 16 } },
    sizing: { risk: 0.0075, notional_cap: 0.2, weight: 1.0 },
    filters: [],
  };
}

const PRESETS: { key: string; label: string; family: string | null; spec: StrategySpec }[] = [
  {
    key: "blank",
    label: "Blank — start from scratch",
    family: null,
    spec: defaultSpec("fleet-60"),
  },
  {
    key: "rule_p",
    label: "Rule P — pump short (base)",
    family: "pump_short",
    spec: {
      name: "pump-short base",
      side: "short",
      market: "crypto_perp",
      universe: "fleet-60",
      fresh: false,
      entry: {
        logic: "AND",
        children: [
          { left: { ind: "ROC", params: { period: 16 } }, op: "ge", right: 0.12 },
          { left: { ind: "close" }, op: "lt", right: { ind: "close", offset: -1 } },
          { left: { ind: "VOL_RATIO", params: { period: 8 } }, op: "ge", right: 2.0 },
        ],
      },
      exit: { time_bars: 16, stop: { mode: "hh", param: 0.0, window: 16 } },
      sizing: { risk: 0.0075, notional_cap: 0.2, weight: 1.0 },
      filters: [],
    },
  },
  {
    key: "rule_p_wick",
    label: "Rule P + upper wick ≥ 30%",
    family: "pump_short",
    spec: {
      name: "pump-short wick30",
      side: "short",
      market: "crypto_perp",
      universe: "fleet-60",
      fresh: false,
      entry: {
        logic: "AND",
        children: [
          { left: { ind: "ROC", params: { period: 16 } }, op: "ge", right: 0.12 },
          { left: { ind: "close" }, op: "lt", right: { ind: "close", offset: -1 } },
          { left: { ind: "VOL_RATIO", params: { period: 8 } }, op: "ge", right: 2.0 },
          { left: { ind: "WICK_FRAC", params: { period: 16 } }, op: "ge", right: 0.3 },
        ],
      },
      exit: { time_bars: 16, stop: { mode: "hh", param: 0.0, window: 16 } },
      sizing: { risk: 0.0075, notional_cap: 0.2, weight: 1.0 },
      filters: [],
    },
  },
  {
    key: "momo",
    label: "Momentum long (breakout)",
    family: "momo_long",
    spec: {
      name: "momentum-long",
      side: "long",
      market: "crypto_perp",
      universe: "fleet-60",
      fresh: false,
      entry: {
        logic: "AND",
        children: [
          { left: { ind: "ROC", params: { period: 16 } }, op: "ge", right: 0.12 },
          { left: { ind: "VOL_RATIO", params: { period: 8 } }, op: "ge", right: 2.5 },
          { left: { ind: "WICK_FRAC", params: { period: 16 } }, op: "le", right: 0.15 },
          { left: { ind: "CLOSE_POS", params: { period: 16 } }, op: "ge", right: 0.8 },
        ],
      },
      exit: { time_bars: 48, stop: { mode: "sig", param: 0.001, window: 16 } },
      sizing: { risk: 0.0075, notional_cap: 0.2, weight: 1.0 },
      filters: [],
    },
  },
  {
    key: "capit",
    label: "Capitulation long (crash buy)",
    family: "capit_long",
    spec: {
      name: "capit-long",
      side: "long",
      market: "crypto_perp",
      universe: "fleet-60",
      fresh: true,
      entry: {
        logic: "AND",
        children: [{ left: { ind: "ROC", params: { period: 96 } }, op: "le", right: -0.2 }],
      },
      exit: { time_bars: 96, stop: { mode: "none", param: 0.0 } },
      sizing: { risk: 0.0075, notional_cap: 0.2, weight: 1.0 },
      filters: [],
    },
  },
];

// ---- recursive editors ----

function OperandEditor({
  value,
  onChange,
  market,
}: {
  value: Operand;
  onChange: (v: Operand) => void;
  market: string;
}) {
  const isInd = typeof value === "object" && value !== null && "ind" in (value as object);
  const inds = useMemo(() => indicatorsForMarket(market), [market]);
  const ind = isInd ? (value as { ind: string }).ind : "";
  const indMeta = ind ? indicatorById(ind) : undefined;

  if (!isInd) {
    return (
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <select
          className={r.input}
          style={{ width: 110 }}
          value="const"
          onChange={() => onChange(defaultOperand())}
        >
          <option value="const">Constant</option>
          <option value="ind">Indicator</option>
        </select>
        <input
          className={r.input}
          type="number"
          step="any"
          value={typeof value === "number" ? value : 0}
          onChange={(e) => onChange(Number(e.target.value))}
          style={{ width: 120 }}
        />
      </div>
    );
  }

  const v = value as { ind: string; params?: Record<string, unknown>; offset?: number };
  const params = v.params ?? {};
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        <select
          className={r.input}
          style={{ width: 110 }}
          value="ind"
          onChange={() => onChange(0)}
        >
          <option value="ind">Indicator</option>
          <option value="const">Constant</option>
        </select>
        <select
          className={r.input}
          style={{ flex: "1 1 200px", minWidth: 180 }}
          value={v.ind}
          onChange={(e) => {
            const m = indicatorById(e.target.value);
            const p: Record<string, unknown> = {};
            for (const pm of m?.params ?? []) p[pm.name] = pm.default;
            onChange({ ind: e.target.value, params: p, offset: v.offset ?? 0 });
          }}
        >
          {Array.from(new Set(inds.map((i) => i.category))).map((cat) => (
            <optgroup key={cat} label={cat}>
              {inds
                .filter((i) => i.category === cat)
                .map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.label}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
        <label style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span className="lbl">offset</span>
          <input
            className={r.input}
            type="number"
            step="1"
            value={v.offset ?? 0}
            onChange={(e) =>
              onChange({ ...v, offset: Number(e.target.value) })
            }
            style={{ width: 70 }}
          />
        </label>
      </div>
      {indMeta && indMeta.params.length > 0 && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", paddingLeft: 4 }}>
          {indMeta.params.map((pm) => (
            <label key={pm.name} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <span className="lbl">{pm.name}</span>
              <input
                className={r.input}
                type={pm.type === "int" ? "number" : "number"}
                step={pm.type === "int" ? 1 : "any"}
                min={pm.min ?? undefined}
                max={pm.max ?? undefined}
                value={
                  params[pm.name] === undefined ? (pm.default as number) : (params[pm.name] as number)
                }
                onChange={(e) => {
                  const raw = e.target.value === "" ? pm.default : Number(e.target.value);
                  onChange({ ...v, params: { ...params, [pm.name]: raw } });
                }}
                style={{ width: 90 }}
              />
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function NodeEditor({
  node,
  onChange,
  onRemove,
  market,
}: {
  node: AnyNode;
  onChange: (n: AnyNode) => void;
  onRemove: () => void;
  market: string;
}) {
  if (isGroup(node)) {
    const g = node;
    return (
      <div
        style={{
          border: "1px solid var(--line-2)",
          borderRadius: 10,
          padding: 12,
          background: "#0a0d12",
        }}
      >
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
          <select
            className={r.input}
            style={{ width: 90 }}
            value={g.logic}
            onChange={(e) => onChange({ ...g, logic: e.target.value as CondGroup["logic"] })}
          >
            {LOGICS.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
          <span className="lbl">group</span>
          <div style={{ flex: 1 }} />
          <button
            className={p.btn}
            style={{ height: 28, padding: "0 10px", fontSize: 12 }}
            onClick={() =>
              onChange({ ...g, children: [...g.children, { logic: "AND", children: [] }] })
            }
          >
            + group
          </button>
          <button
            className={p.btn}
            style={{ height: 28, padding: "0 10px", fontSize: 12 }}
            onClick={() =>
              onChange({
                ...g,
                children: [
                  ...g.children,
                  { left: defaultOperand(), op: "ge", right: 0 },
                ],
              })
            }
          >
            + condition
          </button>
          {onRemove && (
            <button
              className={p.btn}
              style={{ height: 28, padding: "0 10px", fontSize: 12, color: "var(--down)" }}
              onClick={onRemove}
            >
              remove
            </button>
          )}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {g.children.length === 0 && (
            <div className="lbl" style={{ padding: "8px 0" }}>
              Empty group — add a condition or nested group.
            </div>
          )}
          {g.children.map((c, i) => (
            <NodeEditor
              key={i}
              node={c}
              market={market}
              onChange={(n) => {
                const next = [...g.children];
                next[i] = n;
                onChange({ ...g, children: next });
              }}
              onRemove={() => {
                const next = g.children.filter((_, j) => j !== i);
                onChange({ ...g, children: next });
              }}
            />
          ))}
        </div>
      </div>
    );
  }

  const c = node as CondNode;
  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        alignItems: "flex-start",
        flexWrap: "wrap",
        padding: "8px 10px",
        border: "1px solid var(--line)",
        borderRadius: 8,
        background: "#0d1117",
      }}
    >
      <div style={{ flex: "1 1 260px", minWidth: 220 }}>
        <OperandEditor
          value={c.left}
          market={market}
          onChange={(v) => onChange({ ...c, left: v })}
        />
      </div>
      <select
        className={r.input}
        style={{ width: 150 }}
        value={c.op}
        onChange={(e) => onChange({ ...c, op: e.target.value })}
      >
        {OPS.map((o) => (
          <option key={o.v} value={o.v}>
            {o.l}
          </option>
        ))}
      </select>
      <div style={{ flex: "1 1 260px", minWidth: 220 }}>
        <OperandEditor
          value={c.right}
          market={market}
          onChange={(v) => onChange({ ...c, right: v })}
        />
      </div>
      <button
        className={p.btn}
        style={{ height: 32, padding: "0 10px", fontSize: 12, color: "var(--down)" }}
        onClick={onRemove}
      >
        ×
      </button>
    </div>
  );
}

// ---- main component ----


export default function Compose() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [sp] = useSearchParams();
  const botId = sp.get("bot");
  const startFamily = sp.get("family");
  const { data: bot, loading: botLoading } = useMyBot(botId);
  const { data: universes } = useUniverses();

  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [started, setStarted] = useState(false);
  const [presetKey, setPresetKey] = useState<string>("blank");
  const [spec, setSpec] = useState<StrategySpec>(defaultSpec("fleet-60"));
  const [seeded, setSeeded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const universeList = universes ?? [];
  const selectedUniverse = universeList.find((u) => u.slug === spec.universe);
  const marketMeta = CATALOG.markets.find((m) => m.id === spec.market);
  const familySlug = PRESETS.find((pr) => pr.key === presetKey)?.family ?? null;

  // seed
  useEffect(() => {
    if (seeded || botLoading) return;
    if (botId && !bot) return;
    if (bot) {
      setName(bot.name);
      const s = (bot.spec as StrategySpec | null) ?? null;
      if (s && s.entry) {
        setSpec({ ...defaultSpec(s.universe ?? "fleet-60"), ...s, name: bot.name });
        const pk = PRESETS.find((pr) => pr.family === bot.family_slug && JSON.stringify(pr.spec.entry) === JSON.stringify(s.entry))?.key;
        setPresetKey(pk ?? "blank");
      } else {
        setSpec(defaultSpec("fleet-60"));
      }
      setSeeded(true);
      return;
    }
    const slug = startFamily && ["pump_short", "capit_long", "momo_long"].includes(startFamily)
      ? startFamily
      : null;
    const pk = slug
      ? PRESETS.find((pr) => pr.family === slug)?.key ?? "blank"
      : "blank";
    setPresetKey(pk);
    const base = PRESETS.find((pr) => pr.key === pk)?.spec ?? defaultSpec("fleet-60");
    setName("New strategy");
    setSpec({ ...base, name: "New strategy" });
    setSeeded(true);
  }, [bot, botId, botLoading, seeded, startFamily]);

  // ensure universe list loaded -> default slug
  useEffect(() => {
    if (!seeded) return;
    if (universeList.length && !universeList.find((u) => u.slug === spec.universe)) {
      setSpec((s) => ({ ...s, universe: universeList[0].slug }));
    }
  }, [universeList, seeded, spec.universe]);

  const updateFilter = (kind: string, on: boolean) => {
    setSpec((s) => {
      const filters = s.filters.filter((f) => f.kind !== kind);
      if (on) filters.push({ kind });
      return { ...s, filters };
    });
  };
  const hasFilter = (kind: string) => spec.filters.some((f) => f.kind === kind);
  const filterVal = (kind: string, key: string): unknown =>
    (spec.filters.find((f) => f.kind === kind) as Record<string, unknown> | undefined)?.[key];

  const setUniverseFilterOnly = (raw: string) => {
    setSpec((s) => {
      const filters = s.filters.filter((f) => f.kind !== "universe");
      const only = raw
        .split(",")
        .map((x) => x.trim().toUpperCase())
        .filter(Boolean);
      if (only.length) filters.push({ kind: "universe", only });
      return { ...s, filters };
    });
  };

  const loadPreset = (key: string) => {
    setPresetKey(key);
    const pr = PRESETS.find((p) => p.key === key);
    if (!pr || key === "blank") return;
    setSpec({ ...pr.spec, name: name || pr.spec.name });
  };

  const save = async (toTraining: boolean) => {
    if (!user) {
      nav("/signin");
      return;
    }
    setErr(null);
    if (!name.trim()) {
      setErr("Give the bot a name.");
      return;
    }
    setSaving(true);
    const finalName = name.trim();
    const taken = await botNameTaken(user.id, finalName, bot?.id);
    if (taken.error) {
      setSaving(false);
      setErr(taken.error.message);
      return;
    }
    if (taken.taken) {
      setSaving(false);
      setErr("You already have a bot with that name. Pick another.");
      return;
    }

    const finalSpec: StrategySpec = { ...spec, name: finalName, universe: spec.universe };
    const direction = finalSpec.side === "long" ? "long" : finalSpec.side === "short" ? "short" : "both";
    const uni = universeList.find((u) => u.slug === finalSpec.universe);
    const input = {
      name: finalName,
      family_slug: familySlug,
      universe_id: uni?.id ?? bot?.universe_id ?? null,
      direction,
      params: {},
      spec: finalSpec as unknown as Record<string, unknown>,
    };

    let id = bot?.id ?? null;
    if (bot) {
      const { error } = await updateDraftBot({ id: bot.id, ...input });
      if (error) {
        setSaving(false);
        setErr(error.message);
        return;
      }
    } else {
      const { data, error } = await createDraftBot({ owner: user.id, ...input });
      if (error || !data) {
        setSaving(false);
        setErr(error?.message ?? "Could not save the bot.");
        return;
      }
      id = data.id;
    }

    if (!toTraining) {
      setSaving(false);
      nav("/build");
      return;
    }
    if (!id) {
      setSaving(false);
      setErr("Could not resolve the saved bot.");
      return;
    }
    const latest = await fetchLatestBacktest(id);
    if (latest.error) {
      setSaving(false);
      setErr(latest.error.message);
      return;
    }
    if (latest.data && (latest.data.status === "pending" || latest.data.status === "running")) {
      await setBotStage(id, "training");
      setSaving(false);
      nav(withBot("/build/training", id));
      return;
    }
    const { error: stageErr } = await setBotStage(id, "training");
    if (stageErr) {
      setSaving(false);
      setErr(stageErr.message);
      return;
    }
    const { error } = await createBacktest({
      bot_id: id,
      universe_id: uni?.id ?? bot?.universe_id ?? null,
    });
    if (error) {
      await setBotStage(id, "draft");
      setSaving(false);
      setErr(error.message);
      return;
    }
    setSaving(false);
    nav(withBot("/build/training", id));
  };

  if (botLoading) return <StepLoading step={1} />;
  if (botId && !bot) return <MissingBot step={1} />;

  return (
    <>
      <div className={p.crumb}>
        <span className="lk" onClick={() => nav("/build")}>Build</span> / <b>{name || "New bot"}</b>
      </div>
      <Steps current={1} />
      <div className={p.body}>
        {!started && (
          <section style={{ maxWidth: 720, padding: "48px 0" }}>
            <h1 className={p.title} style={{ fontSize: 34 }}>Compose</h1>
            <div className={p.subtitle} style={{ marginTop: 8 }}>
              Describe the strategy you want in plain English. We'll parse it into rules you can refine.
            </div>
            <div style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 12 }}>
              <input
                className={r.input}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Strategy name"
                style={{ fontSize: 18, height: 52 }}
              />
              <textarea
                className={r.input}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder='e.g. "short pumps: price up 12% in 4h, red candle, volume 2x, hold 16 bars"'
                rows={3}
                style={{ resize: "vertical", padding: 12, fontFamily: "inherit" }}
              />
<div style={{ display: "flex", gap: 10 }}>
                <button
                  className={`${p.btn} ${p.pri}`}
                  style={{ height: 46 }}
                  onClick={() => {
                    const text = prompt || name;
                    // Always use the API which uses the backend-configured Anthropic key
                    // NO FALLBACKS - if API errors or key not configured, show error
                    fetch(`/api/parse-strategy?text=${encodeURIComponent(text)}`)
                      .then((r) => r.json())
                      .then((data) => {
                        if (data.error) {
                          // Claude API failed or key not configured - show error, still present manual screen
                          setSpec(defaultSpec("fleet-60"));
                          setPresetKey("blank");
                          setStarted(true);
                          setErr(data.error || "Unknown parsing error");
                          return;
                        }
                        // Use Claude-parsed spec - validate and set
                        const cspec = data.spec as StrategySpec;
                        let spec = defaultSpec("fleet-60");
                        spec.name = cspec.name || "Claude-parsed";
                        spec.side = cspec.side || "short";
                        spec.market = cspec.market || "crypto_perp";
                        spec.universe = cspec.universe || "fleet-60";
                        spec.fresh = cspec.fresh ?? false;
                        
                        // Set entry from Claude
                        if (cspec.entry && cspec.entry.logic && cspec.entry.children) {
                          spec.entry = cspec.entry;
                        } else {
                          spec.entry = { logic: "AND", children: [] };
                        }
                        
                        // Set exit from Claude
                        if (cspec.exit) {
                          spec.exit = { ...defaultSpec("fleet-60").exit, ...cspec.exit };
                        } else {
                          spec.exit = defaultSpec("fleet-60").exit;
                        }
                        
                        // Set sizing from Claude
                        if (cspec.sizing) {
                          spec.sizing = { ...defaultSpec("fleet-60").sizing, ...cspec.sizing };
                        } else {
                          spec.sizing = defaultSpec("fleet-60").sizing;
                        }
                        
                        spec.filters = cspec.filters || [];
                        
                        setSpec(spec);
                        setPresetKey("blank");
                        setStarted(true);
                        setErr(null);
                      })
                      .catch(() => {
                        // Error contacting API - no fallback to local parsing
                        setSpec(defaultSpec("fleet-60"));
                        setPresetKey("blank");
                        setStarted(true);
                        setErr("Could not reach parsing service");
                      });
                  }}
                >
                  Parse & build
                </button>
                <button
                  className={p.btn}
                  style={{ height: 46 }}
                  onClick={() => {
                    setSpec(defaultSpec("fleet-60"));
                    setPresetKey("blank");
                    setStarted(true);
                  }}
                >
                  Skip — build manually
                </button>
              </div>
            </div>
            </section>
          )}
        {started && (

        <section style={{ display: "flex", flexWrap: "wrap", gap: 32, paddingTop: 28 }}>
          <div style={{ flex: "999 1 620px", minWidth: 0 }}>
            {/* Name */}
            <div style={{ paddingBottom: 28, borderBottom: "1px solid var(--line)" }}>
              <div className={r.label}>Strategy name</div>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Name this bot"
                style={{ background: "transparent", border: "none", color: "var(--fg)", fontSize: 36, fontWeight: 500, letterSpacing: "-0.02em", width: "100%", marginTop: 6, outline: "none" }}
              />
            </div>

            {bot?.stage === "deployed" && (
              <div className={r.statusCard} style={{ marginTop: 20 }}>
                <span className="downDot" style={{ background: "#d29922" }} />
                <div className="lbl" style={{ lineHeight: 1.5 }}>
                  This bot is deployed. Saving any change takes it off the fleet and back to Draft.
                </div>
              </div>
            )}

            {/* Preset */}
            <div className={r.formRow}>
              <h2 className={r.h2}>Starting point</h2>
              <div className={r.label} style={{ margin: "4px 0 12px" }}>Load a preset, then edit freely. Or start blank.</div>
              <select
                className={r.input}
                value={presetKey}
                onChange={(e) => loadPreset(e.target.value)}
                style={{ width: "100%", maxWidth: 420 }}
              >
                {PRESETS.map((pr) => (
                  <option key={pr.key} value={pr.key}>
                    {pr.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Market + Universe */}
            <div className={r.formRow}>
              <h2 className={r.h2}>Market &amp; universe</h2>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 14, marginTop: 12 }}>
                <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <span className={r.label}>Market</span>
                  <select
                    className={r.input}
                    value={spec.market}
                    onChange={(e) => setSpec((s) => ({ ...s, market: e.target.value }))}
                  >
                    {CATALOG.markets.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                  <span className="lbl">{marketMeta?.provides.join(", ")}</span>
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <span className={r.label}>Universe</span>
                  <select
                    className={r.input}
                    value={spec.universe}
                    onChange={(e) => setSpec((s) => ({ ...s, universe: e.target.value }))}
                  >
                    {universeList.map((u) => (
                      <option key={u.id} value={u.slug}>
                        {u.name ?? u.slug}
                      </option>
                    ))}
                  </select>
                  <span className="lbl">{selectedUniverse?.description ?? ""}</span>
                </label>
              </div>
            </div>

            {/* Side / fresh / sizing */}
            <div className={r.formRow}>
              <h2 className={r.h2}>Direction &amp; sizing</h2>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 14, marginTop: 12 }}>
                <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <span className={r.label}>Side</span>
                  <select
                    className={r.input}
                    value={spec.side}
                    onChange={(e) => setSpec((s) => ({ ...s, side: e.target.value as StrategySpec["side"] }))}
                  >
                    <option value="short">Short</option>
                    <option value="long">Long</option>
                    <option value="both">Both</option>
                  </select>
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <span className={r.label}>Fresh (fire once)</span>
                  <select
                    className={r.input}
                    value={spec.fresh ? "yes" : "no"}
                    onChange={(e) => setSpec((s) => ({ ...s, fresh: e.target.value === "yes" }))}
                  >
                    <option value="no">No — every bar</option>
                    <option value="yes">Yes — only on first true bar</option>
                  </select>
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <span className={r.label}>Risk / trade</span>
                  <input
                    className={r.input}
                    type="number"
                    step="0.0001"
                    value={spec.sizing.risk}
                    onChange={(e) =>
                      setSpec((s) => ({ ...s, sizing: { ...s.sizing, risk: Number(e.target.value) } }))
                    }
                  />
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <span className={r.label}>Notional cap</span>
                  <input
                    className={r.input}
                    type="number"
                    step="0.01"
                    value={spec.sizing.notional_cap}
                    onChange={(e) =>
                      setSpec((s) => ({ ...s, sizing: { ...s.sizing, notional_cap: Number(e.target.value) } }))
                    }
                  />
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <span className={r.label}>Weight</span>
                  <input
                    className={r.input}
                    type="number"
                    step="0.1"
                    value={spec.sizing.weight}
                    onChange={(e) =>
                      setSpec((s) => ({ ...s, sizing: { ...s.sizing, weight: Number(e.target.value) } }))
                    }
                  />
                </label>
              </div>
            </div>

            {/* Entry conditions */}
            <div className={r.formRow}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <h2 className={r.h2}>Entry conditions</h2>
                <span className="lbl">{spec.entry.children.length} top-level</span>
              </div>
              <div className={r.label} style={{ margin: "4px 0 12px" }}>
                Compose the condition tree. Indicators available depend on the market.
              </div>
              <NodeEditor
                node={spec.entry}
                market={spec.market}
                onChange={(n) => setSpec((s) => ({ ...s, entry: n as CondGroup }))}
                onRemove={() => {}}
              />
            </div>

            {/* Exit */}
            <div className={r.formRow}>
              <h2 className={r.h2}>Exit</h2>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 14, marginTop: 12 }}>
                <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <span className={r.label}>Max hold (bars)</span>
                  <input
                    className={r.input}
                    type="number"
                    step="1"
                    value={spec.exit.time_bars}
                    onChange={(e) =>
                      setSpec((s) => ({ ...s, exit: { ...s.exit, time_bars: Number(e.target.value) } }))
                    }
                  />
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <span className={r.label}>Stop mode</span>
                  <select
                    className={r.input}
                    value={spec.exit.stop.mode}
                    onChange={(e) =>
                      setSpec((s) => ({ ...s, exit: { ...s.exit, stop: { ...s.exit.stop, mode: e.target.value } } }))
                    }
                  >
                    {STOP_MODES.map((m) => (
                      <option key={m.v} value={m.v}>
                        {m.l}
                      </option>
                    ))}
                  </select>
                </label>
                {spec.exit.stop.mode === "hh" && (
                  <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span className={r.label}>Window (bars)</span>
                    <input
                      className={r.input}
                      type="number"
                      step="1"
                      value={spec.exit.stop.window ?? 16}
                      onChange={(e) =>
                        setSpec((s) => ({
                          ...s,
                          exit: { ...s.exit, stop: { ...s.exit.stop, window: Number(e.target.value) } },
                        }))
                      }
                    />
                  </label>
                )}
                {spec.exit.stop.mode === "dstop" && (
                  <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span className={r.label}>Disaster stop (fraction)</span>
                    <input
                      className={r.input}
                      type="number"
                      step="0.001"
                      value={spec.exit.stop.param ?? 0}
                      onChange={(e) =>
                        setSpec((s) => ({
                          ...s,
                          exit: { ...s.exit, stop: { ...s.exit.stop, param: Number(e.target.value) } },
                        }))
                      }
                    />
                  </label>
                )}
                {spec.exit.stop.mode === "sig" && (
                  <>
                    <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      <span className={r.label}>Window (bars)</span>
                      <input
                        className={r.input}
                        type="number"
                        step="1"
                        value={spec.exit.stop.window ?? 16}
                        onChange={(e) =>
                          setSpec((s) => ({
                            ...s,
                            exit: { ...s.exit, stop: { ...s.exit.stop, window: Number(e.target.value) } },
                          }))
                        }
                      />
                    </label>
                    <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      <span className={r.label}>Buffer (fraction)</span>
                      <input
                        className={r.input}
                        type="number"
                        step="0.0001"
                        value={spec.exit.stop.param ?? 0.001}
                        onChange={(e) =>
                          setSpec((s) => ({
                            ...s,
                            exit: { ...s.exit, stop: { ...s.exit.stop, param: Number(e.target.value) } },
                          }))
                        }
                      />
                    </label>
                  </>
                )}
                <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <span className={r.label}>Take profit (fraction, optional)</span>
                  <input
                    className={r.input}
                    type="number"
                    step="0.01"
                    value={spec.exit.take_profit ?? ""}
                    onChange={(e) => {
                      const v = e.target.value === "" ? undefined : Number(e.target.value);
                      setSpec((s) => ({ ...s, exit: { ...s.exit, take_profit: v } }));
                    }}
                  />
                </label>
              </div>
            </div>

            {/* Filters */}
            <div className={r.formRow}>
              <h2 className={r.h2}>Filters</h2>
              <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 12 }}>
                <label style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <input
                    type="checkbox"
                    checked={hasFilter("btc_bear")}
                    onChange={(e) => updateFilter("btc_bear", e.target.checked)}
                  />
                  <span>BTC bear regime required</span>
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <input
                    type="checkbox"
                    checked={hasFilter("regime_veto")}
                    onChange={(e) => updateFilter("regime_veto", e.target.checked)}
                  />
                  <span>Regime veto</span>
                  {hasFilter("regime_veto") && (
                    <input
                      className={r.input}
                      type="number"
                      step="0.01"
                      value={(filterVal("regime_veto", "threshold") as number) ?? 0}
                      onChange={(e) =>
                        setSpec((s) => ({
                          ...s,
                          filters: s.filters.map((f) =>
                            f.kind === "regime_veto" ? { ...f, threshold: Number(e.target.value) } : f,
                          ),
                        }))
                      }
                      style={{ width: 100 }}
                    />
                  )}
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <span className={r.label}>Universe only (comma-separated tickers)</span>
                  <input
                    className={r.input}
                    value={((filterVal("universe", "only") as string[] | undefined) ?? []).join(", ")}
                    onChange={(e) => setUniverseFilterOnly(e.target.value)}
                    placeholder="e.g. BTC, ETH"
                  />
                </label>
              </div>
            </div>
          </div>

          {/* Sidebar */}
          <div style={{ flex: "1 1 320px", minWidth: 0, display: "flex", flexDirection: "column", gap: 16, paddingTop: 4 }}>
            <div className="card" style={{ padding: 20 }}>
              <div className={r.label}>Live preview</div>
              <div style={{ fontSize: 15, fontWeight: 500, marginTop: 6 }}>{name.trim() || "New strategy"}</div>
              <div className="lbl" style={{ marginTop: 2 }}>
                {familySlug ? familySlug : "Custom"} · {spec.side} · {spec.market}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 16 }}>
                <div className={r.label}>Entry</div>
                <div style={{ fontSize: 13, lineHeight: 1.5, color: "var(--muted)" }}>
                  {spec.entry.children.length
                    ? `${spec.entry.logic} of ${spec.entry.children.length} condition(s)`
                    : "No conditions yet."}
                </div>
                <div className={r.label} style={{ marginTop: 8 }}>Exit</div>
                <div style={{ fontSize: 13, lineHeight: 1.5, color: "var(--muted)" }}>
                  {spec.exit.time_bars} bars · stop {spec.exit.stop.mode}
                </div>
                <div className="lbl" style={{ marginTop: 8 }}>
                  Universe: {spec.universe} · {selectedUniverse ? selectedUniverse.name : ""}
                </div>
              </div>
            </div>

            <div className="card" style={{ padding: 20 }}>
              <div className={r.label}>Universe</div>
              <div className="num" style={{ fontSize: 32, marginTop: 6 }}>
                {selectedUniverse ? "—" : 0}
              </div>
              <div className="lbl" style={{ marginTop: 2 }}>{selectedUniverse?.name ?? spec.universe}</div>
            </div>

            <button
              className={`${p.btn} ${p.pri}`}
              style={{ height: 48, fontSize: 14 }}
              disabled={saving}
              onClick={() => save(true)}
            >
              {saving ? "Saving…" : "Start training"}
            </button>
            <button
              className={p.btn}
              style={{ height: 44 }}
              disabled={saving}
              onClick={() => save(false)}
            >
              {saving ? "Saving…" : bot ? "Save draft" : "Sign in to save"}
            </button>
            {!user && <div className="lbl">Sign in to save this strategy to your roster.</div>}
            {err && <div style={{ color: "var(--down, #ff5c6c)", fontSize: 13 }}>{err}</div>}
          </div>
        </section>
        )}
      </div>
    </>
  );
}
