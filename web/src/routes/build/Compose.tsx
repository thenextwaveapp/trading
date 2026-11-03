import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../auth";
import {
  autosaveBot,
  botNameTaken,
  createBacktest,
  createDraftBot,
  saveBotVersion,
  createUniverse,
  fetchLatestBacktest,
  setBotStage,
  updateDraftBot,
  updateUniverse,
  useCoins,
  useMyBot,
  useUniverse,
  useUniverses,
} from "../../db/queries";
import {
  CATALOG,
  SPEC_GROUPS,
  blockingIssues,
  defaultSpec as catalogDefaultSpec,
  getPath,
  indicatorById,
  indicatorsForMarket,
  paramsForGroup,
  setPath,
  specIssues,
  specParam,
  visibleParam,
} from "../../lib/catalog";
import type { Visibility } from "../../db/types";
import { DEFAULT_BOT_COLOR, FLEET_PALETTE, botColor } from "../../lib/brand";
import { BackBar } from "../../components/cells";
import { identicon } from "../../lib/format";
import { buildStrategyRows } from "../BotProfile";
import p from "../pages.module.css";
import r from "./build.module.css";
import { MissingBot, StepLoading } from "./parts";
import Steps from "./Steps";
import { withBot } from "./stages";

// ---- types matching core/expr.py + core/strategy.py ----

interface IndOperand {
  ind: string;
  params?: Record<string, unknown>;
  offset?: number;
  tf?: string;        // read the indicator on another timeframe
  symbol?: string;    // read the indicator on another instrument (ticker)
}
interface ArithOperand {
  op: "add" | "sub" | "mul" | "div";
  left: Operand;
  right: Operand;
  offset?: number;
}
type Operand = number | IndOperand | ArithOperand;

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

function validOperand(o: Operand): boolean {
  if (typeof o === "number" && Number.isFinite(o)) return true;
  if (typeof o === "object" && o !== null) {
    if ("ind" in o) {
      const v = o as IndOperand;
      return typeof v.ind === "string" && v.ind.length > 0;
    }
    if ("op" in o) {
      const a = o as ArithOperand;
      return ARITH.some((x) => x.v === a.op)
        && validOperand(a.left) && validOperand(a.right);
    }
  }
  return false;
}

function validateEntry(node: AnyNode): string | null {
  if (!isGroup(node)) return "Entry must be a condition group.";
  if (node.children.length === 0) return "Add at least one entry condition.";
  for (const c of node.children) {
    if (isGroup(c)) {
      const e = validateEntry(c);
      if (e) return e;
    } else {
      const n = c as CondNode;
      if (!n || typeof n !== "object") return "Invalid condition.";
      if (!OPS.some((o) => o.v === n.op)) return "Invalid operator in an entry condition.";
      if (!validOperand(n.left) || !validOperand(n.right)) return "Each condition needs valid left/right operands.";
    }
  }
  return null;
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

interface TimingCfg {
  hours_utc: number[];
  days_utc: number[];
  dates?: string[];
}

interface StrategySpec {
  name: string;
  side: "long" | "short" | "both";
  market: string;
  universe: string;
  timeframe: string;
  fresh: boolean;
  entry: CondGroup;
  timing: TimingCfg;
  exit: ExitCfg;
  sizing: SizingCfg;
  filters: FilterCfg[];
  // side: "both" — the short book's entry/exit (the long book stays in
  // entry/exit above). Serialized to entry_long/exit_long/entry_short/exit_short.
  entry_short?: CondGroup;
  exit_short?: ExitCfg;
}

// State (entry/exit = long when both) -> wire spec. A two-sided bot emits
// entry_long/exit_long/entry_short/exit_short and drops the bare entry/exit;
// a single-side bot drops the short book.
function toWireSpec(spec: StrategySpec): Record<string, unknown> {
  const out = { ...spec } as Record<string, unknown>;
  if (spec.side === "both") {
    out.entry_long = spec.entry;
    out.exit_long = spec.exit;
    out.entry_short = spec.entry_short ?? { logic: "AND", children: [] };
    out.exit_short = spec.exit_short ?? spec.exit;
    delete out.entry;
    delete out.exit;
  } else {
    delete out.entry_short;
    delete out.exit_short;
  }
  return out;
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

const LOGICS = ["AND", "OR", "NOT"] as const;
const ARITH = [
  { v: "add", l: "+" },
  { v: "sub", l: "−" },
  { v: "mul", l: "×" },
  { v: "div", l: "÷" },
] as const;
const EXIT_CUSTOM = new Set(["exit.trailing.k", "exit.trailing.natr"]);
// Sentinel universe value for "building a custom subset" (not a real slug).
const CUSTOM_UNI = "__custom__";
// Universes/coins are tagged by asset class ('crypto' / 'equity'), while the
// market catalog ids are finer ('crypto_perp', 'crypto_spot', 'equity', …).
const ASSET_CLASS = (marketId: string): string => (marketId.startsWith("crypto") ? "crypto" : marketId);

function defaultOperand(): Operand {
  return { ind: "ROC", params: { period: 16 }, offset: 0 };
}

// Normalize a parsed/assistant-supplied condition tree into the internal shape.
// Shared by the NL-parse path and the assistant's structured hand-off so both
// produce an identical spec (no second guess, no lossy round-trip).
const OP_MAP: Record<string, CondNode["op"]> = {
  ">": "gt", "gt": "gt", ">=": "ge", "ge": "ge", "<": "lt", "lt": "lt",
  "<=": "le", "le": "le", "==": "eq", "=": "eq", "eq": "eq", "!=": "ne", "ne": "ne",
  "crosses_above": "crosses_above", "crosses_below": "crosses_below",
};
const ARITH_MAP: Record<string, ArithOperand["op"]> = {
  add: "add", "+": "add", sub: "sub", "-": "sub",
  mul: "mul", "*": "mul", div: "div", "/": "div",
};
function normOperand(o: any): Operand {
  if (typeof o === "number" && Number.isFinite(o)) return o;
  if (typeof o === "string" && o.trim() !== "" && Number.isFinite(Number(o))) return Number(o);
  if (o && typeof o === "object" && o.left !== undefined && o.right !== undefined
      && ARITH_MAP[String(o.op)]) {
    const out: ArithOperand = {
      op: ARITH_MAP[String(o.op)],
      left: normOperand(o.left),
      right: normOperand(o.right),
    };
    if (typeof o.offset === "number" && o.offset !== 0) out.offset = o.offset;
    return out;
  }
  if (o && typeof o === "object" && typeof o.ind === "string") {
    const rawInd = o.ind.trim();
    const found = indicatorById(rawInd) ?? indicatorById(rawInd.toUpperCase()) ?? indicatorById(rawInd.toLowerCase());
    const ind = found ? found.id : rawInd;
    const params: Record<string, unknown> = {};
    if (o.params && typeof o.params === "object") {
      for (const [k, v] of Object.entries(o.params)) {
        params[k] = typeof v === "string" && Number.isFinite(Number(v)) ? Number(v) : v;
      }
    } else if (found?.params?.length) {
      for (const pm of found.params) params[pm.name] = pm.default;
    }
    const out: IndOperand = { ind, params, offset: typeof o.offset === "number" ? o.offset : 0 };
    if (typeof o.tf === "string" && o.tf) out.tf = o.tf;
    if (typeof o.symbol === "string" && o.symbol) out.symbol = o.symbol;
    return out;
  }
  return defaultOperand();
}
function normGroup(g: any): CondGroup {
  const logic: CondGroup["logic"] = g && (g.logic === "OR" || g.logic === "NOT") ? g.logic : "AND";
  const rawChildren = Array.isArray(g?.children) ? g.children : [];
  const children: AnyNode[] = rawChildren
    .map((c: any): AnyNode | null => {
      if (!c || typeof c !== "object") return null;
      if (Array.isArray(c.children)) return normGroup(c);
      if (c.left === undefined || c.right === undefined) return null;
      const op = OP_MAP[String(c.op ?? c.operator ?? "ge")] ?? "ge";
      return { left: normOperand(c.left), op, right: normOperand(c.right) };
    })
    .filter((x: AnyNode | null): x is AnyNode => x !== null);
  return { logic, children };
}

function blankSpec(universe: string): StrategySpec {
  const spec = catalogDefaultSpec<Record<string, unknown>>(universe);
  return { name: "", ...spec, universe, filters: [] } as unknown as StrategySpec;
}

function groupLabel(id: string): string {
  return SPEC_GROUPS.find((g) => g.id === id)?.label ?? id;
}

function mergeSpec(base: StrategySpec, incoming: Partial<StrategySpec>): StrategySpec {
  const inc = incoming as any;
  // a two-sided wire spec carries entry_long/exit_long/entry_short/exit_short;
  // fold it back into the editor's shape (entry/exit = long book, + *_short).
  const out: any = {
    ...base,
    ...incoming,
    entry: inc.entry ?? inc.entry_long ?? base.entry,
    timing: { ...base.timing, ...(incoming.timing ?? {}) },
    exit: { ...base.exit, ...(inc.exit ?? inc.exit_long ?? {}) },
    sizing: { ...base.sizing, ...(incoming.sizing ?? {}) },
    filters: incoming.filters ?? base.filters,
    entry_short: inc.entry_short ?? base.entry_short,
    exit_short: inc.exit_short
      ? { ...base.exit, ...inc.exit_short }
      : base.exit_short,
  };
  delete out.entry_long;
  delete out.exit_long;
  return out as StrategySpec;
}

const PRESETS: { key: string; label: string; family: string | null; spec: StrategySpec }[] = [
  {
    key: "blank",
    label: "Blank — start from scratch",
    family: null,
    spec: blankSpec("fleet-60"),
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
      timeframe: "15m",
      fresh: false,
      timing: { hours_utc: [], days_utc: [] },
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
      timeframe: "15m",
      fresh: false,
      timing: { hours_utc: [], days_utc: [] },
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
      timeframe: "15m",
      fresh: false,
      timing: { hours_utc: [], days_utc: [] },
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
      timeframe: "15m",
      fresh: true,
      timing: { hours_utc: [], days_utc: [] },
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
  const isExpr = typeof value === "object" && value !== null && "op" in (value as object);
  const mode = isInd ? "ind" : isExpr ? "expr" : "const";
  const inds = useMemo(() => indicatorsForMarket(market), [market]);
  const ind = isInd ? (value as { ind: string }).ind : "";
  const indMeta = ind ? indicatorById(ind) : undefined;
  const tfOptions = ((specParam("timeframe")?.options ?? []) as {
    value: string; label: string;
  }[]);

  const setMode = (m: string) => {
    if (m === mode) return;
    if (m === "const") onChange(0);
    else if (m === "ind") onChange(defaultOperand());
    else onChange({ op: "sub", left: defaultOperand(), right: 0 });
  };
  const modeSelect = (
    <select className={r.input} style={{ width: 110 }} value={mode}
      onChange={(e) => setMode(e.target.value)}>
      <option value="const">Constant</option>
      <option value="ind">Indicator</option>
      <option value="expr">Expression</option>
    </select>
  );

  if (mode === "const") {
    return (
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        {modeSelect}
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

  if (mode === "expr") {
    const e = value as ArithOperand;
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {modeSelect}
        <div style={{
          display: "flex", flexDirection: "column", gap: 6,
          border: "1px solid var(--line-2)", borderRadius: 8, padding: 8,
          background: "#0a0d12",
        }}>
          <OperandEditor value={e.left} market={market}
            onChange={(l) => onChange({ ...e, left: l })} />
          <select className={r.input} style={{ width: 70, alignSelf: "flex-start" }}
            value={e.op}
            onChange={(ev) => onChange({ ...e, op: ev.target.value as ArithOperand["op"] })}>
            {ARITH.map((a) => (
              <option key={a.v} value={a.v}>{a.l}</option>
            ))}
          </select>
          <OperandEditor value={e.right} market={market}
            onChange={(rr) => onChange({ ...e, right: rr })} />
        </div>
      </div>
    );
  }

  const v = value as IndOperand;
  const params = v.params ?? {};
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        {modeSelect}
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
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", paddingLeft: 4, alignItems: "flex-end" }}>
        {(indMeta?.params ?? []).map((pm) => (
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
        <label style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span className="lbl">offset</span>
          <input
            className={r.input}
            type="number"
            step="1"
            value={v.offset ?? 0}
            onChange={(e) => onChange({ ...v, offset: Number(e.target.value) })}
            style={{ width: 70 }}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span className="lbl">timeframe</span>
          <select
            className={r.input}
            value={v.tf ?? ""}
            onChange={(e) => onChange({ ...v, tf: e.target.value || undefined })}
            style={{ width: 90 }}
          >
            <option value="">base</option>
            {tfOptions.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span className="lbl">symbol</span>
          <input
            className={r.input}
            value={v.symbol ?? ""}
            placeholder="base"
            onChange={(e) => onChange({ ...v, symbol: e.target.value.trim() || undefined })}
            style={{ width: 90 }}
          />
        </label>
      </div>
      {(v.tf || v.symbol) && (
        <span className="lbl" style={{ fontSize: 11, paddingLeft: 4 }}>
          Reads {v.symbol || "this instrument"} on the {v.tf || "base"} timeframe,
          aligned to the most recent closed bar.
        </span>
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


// Required-field marker (red asterisk) and an optional-section tag, so the
// Build form reads at a glance: what you must set vs. what has sane defaults.
function Req() {
  return <span title="Required" style={{ color: "var(--down)", marginLeft: 3 }}>*</span>;
}
function Opt() {
  return <span className="lbl" style={{ fontWeight: 400, marginLeft: 7, fontSize: 12 }}>· optional</span>;
}


function DirTabs({ dir, onDir }: {
  dir: "long" | "short";
  onDir: (d: "long" | "short") => void;
}) {
  return (
    <div style={{
      display: "inline-flex", gap: 3, marginBottom: 12,
      border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: 3,
    }}>
      {(["long", "short"] as const).map((d) => (
        <button
          key={d}
          type="button"
          onClick={() => onDir(d)}
          style={{
            padding: "5px 14px", fontSize: 13, borderRadius: 4, border: "none",
            cursor: "pointer", fontWeight: dir === d ? 600 : 400,
            background: dir === d ? "var(--accent)" : "transparent",
            color: dir === d ? "#fff" : "var(--muted)",
          }}
        >
          {d === "long" ? "Long book" : "Short book"}
        </button>
      ))}
    </div>
  );
}


function ParamControl({
  spec,
  path,
  onChange,
  showNote = true,
}: {
  spec: StrategySpec;
  path: string;
  onChange: (path: string, value: unknown) => void;
  showNote?: boolean;
}) {
  const p = specParam(path);
  if (!p || p.kind === "condition" || !visibleParam(p, spec)) return null;

  const raw = getPath(spec, path);
  const value = raw === undefined ? p.default : raw;
  const scale = p.percent ? 100 : 1;
  const shown = value === null || value === undefined
    ? ""
    : Number((Number(value) * scale).toFixed(6));
  const set = (next: unknown) => onChange(path, next);
  const label = (
    <span className={r.label}>
      {p.label}
      {p.unit ? <span className="lbl"> ({p.unit})</span> : null}
    </span>
  );

  let control: React.ReactNode;
  if (p.kind === "bool") {
    control = (
      <span style={{ display: "flex", alignItems: "center", gap: 8, minHeight: 36 }}>
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => set(e.target.checked)}
        />
        <span className="lbl">{Boolean(value) ? "On" : "Off"}</span>
      </span>
    );
  } else if (p.kind === "enum") {
    const options = p.options.length
      ? p.options
      : p.choices.map((c) => ({
          value: String(c),
          label: String(c),
          backtest: true,
          live: true,
          status: "ok" as const,
          reason: "",
        }));
    const current = options.find((o) => o.value === String(value));
    control = (
      <>
        <select
          className={r.input}
          value={String(value ?? "")}
          onChange={(e) => set(e.target.value)}
        >
          {options.map((o) => (
            <option
              key={o.value}
              value={o.value}
              disabled={!o.backtest}
              title={o.reason || undefined}
            >
              {o.label}
              {o.backtest ? "" : " — unsupported"}
            </option>
          ))}
        </select>
        {current && !current.backtest && current.reason && (
          <span style={{ color: "#d29922", fontSize: 11 }}>{current.reason}</span>
        )}
      </>
    );
  } else if (p.kind === "int_list") {
    const list = Array.isArray(value) ? (value as number[]) : [];
    const opts = p.options.length
      ? p.options
      : p.choices.map((c) => ({
          value: String(c),
          label: String(c),
          backtest: true,
          live: true,
          status: "ok" as const,
          reason: "",
        }));
    control = (
      <>
        <div className={r.chipRow}>
          {opts.map((o) => {
            const n = Number(o.value);
            const on = list.includes(n);
            return (
              <button
                key={o.value}
                type="button"
                className={`${r.pill} ${on ? r.sel : ""}`}
                style={{ height: 28, fontSize: 12 }}
                onClick={() =>
                  set(
                    (on ? list.filter((x) => x !== n) : [...list, n]).sort(
                      (a, b) => a - b,
                    ),
                  )
                }
              >
                {o.label}
              </button>
            );
          })}
        </div>
        <span className="lbl" style={{ fontSize: 11 }}>
          {list.length ? "Selected; clear all to allow every value." : "All values."}
        </span>
      </>
    );
  } else if (p.kind === "string") {
    control = (
      <input
        className={r.input}
        value={String(value ?? "")}
        onChange={(e) => set(e.target.value)}
      />
    );
  } else {
    const isInt = p.kind === "int";
    control = (
      <input
        className={r.input}
        type="number"
        step={p.percent
          ? (p.step ?? 0.0001) * scale
          : p.step ?? (isInt ? 1 : "any")}
        min={p.min == null ? undefined : p.min * scale}
        max={p.max == null ? undefined : p.max * scale}
        value={shown}
        onChange={(e) => {
          const text = e.target.value;
          if (text === "") {
            set(p.default === null || p.default === undefined ? undefined : p.default);
          } else {
            set(isInt ? Math.trunc(Number(text)) : Number(text) / scale);
          }
        }}
      />
    );
  }

  return (
    <div
      style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}
      title={p.help || undefined}
    >
      {label}
      {control}
      {showNote && p.status !== "ok" && p.reason && (
        <span style={{ color: "#d29922", fontSize: 11, lineHeight: 1.35 }}>
          {p.reason}
        </span>
      )}
    </div>
  );
}

// ---- timing ----
const HOURS = Array.from({ length: 24 }, (_, h) => h);
const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const WEEKDAYS = [0, 1, 2, 3, 4];
const WEEKENDS = [5, 6];

function hourLabel(h: number): string {
  return `${String(h).padStart(2, "0")}:00`;
}

function sameNumbers(a: number[], b: number[]): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i]);
}

function hoursRange(hours: number[]): { from: string; to: string; custom: boolean } {
  const sorted = [...new Set(hours)].sort((a, b) => a - b);
  if (!sorted.length) return { from: "", to: "", custom: false };
  if (sorted.length === 1) {
    return { from: String(sorted[0]), to: String(sorted[0]), custom: false };
  }
  const contiguous = sorted.every((h, i) => i === 0 || h === sorted[i - 1] + 1);
  if (contiguous) {
    return { from: String(sorted[0]), to: String(sorted[sorted.length - 1]), custom: false };
  }
  const gaps = sorted
    .map((h, i) => (i > 0 && h - sorted[i - 1] > 1 ? i - 1 : -1))
    .filter((i) => i >= 0);
  if (gaps.length === 1) {
    const from = sorted[gaps[0] + 1];
    const to = sorted[gaps[0]];
    const wrapped = rangeHours(String(from), String(to)).sort((a, b) => a - b);
    if (sameNumbers(wrapped, sorted)) {
      return { from: String(from), to: String(to), custom: false };
    }
  }
  return { from: String(sorted[0]), to: String(sorted[sorted.length - 1]), custom: true };
}

function rangeHours(from: string, to: string): number[] {
  if (from === "") return [];
  const a = Number(from);
  const b = to === "" ? a : Number(to);
  if (a <= b) return HOURS.slice(a, b + 1);
  return [...HOURS.slice(a), ...HOURS.slice(0, b + 1)];
}

function daysSummary(days: number[]): string {
  const sorted = [...new Set(days)].sort((a, b) => a - b);
  if (!sorted.length) return "Every day";
  if (sameNumbers(sorted, WEEKDAYS)) return "Weekdays";
  if (sameNumbers(sorted, WEEKENDS)) return "Weekends";
  if (sorted.length === 1) return `${DAY_NAMES[sorted[0]]}s`;
  return sorted.map((d) => DAY_NAMES[d]).join(", ");
}

function TimingControl({
  hours,
  days,
  dates,
  onHours,
  onDays,
  onDates,
}: {
  hours: number[];
  days: number[];
  dates: string[];
  onHours: (hours: number[]) => void;
  onDays: (days: number[]) => void;
  onDates: (dates: string[]) => void;
}) {
  const range = hoursRange(hours);
  const [dateDraft, setDateDraft] = useState("");
  const addDate = () => {
    const v = dateDraft.trim();
    if (v && !dates.includes(v)) onDates([...dates, v]);
    setDateDraft("");
  };
  return (
    <div className={r.timingGrid}>
      <label>
        <span className={r.label}>From (UTC)</span>
        <div className={r.timeRow}>
          <select
            className={r.input}
            value={range.from}
            onChange={(e) => {
              const from = e.target.value;
              onHours(from === "" ? [] : rangeHours(from, range.to));
            }}
          >
            <option value="">All hours</option>
            {HOURS.map((h) => (
              <option key={h} value={h}>{hourLabel(h)}</option>
            ))}
          </select>
          <span className="lbl">to</span>
          <select
            className={r.input}
            value={range.to}
            disabled={range.from === ""}
            onChange={(e) => onHours(rangeHours(range.from, e.target.value))}
          >
            {HOURS.map((h) => (
              <option key={h} value={h}>{hourLabel(h)}</option>
            ))}
          </select>
        </div>
        <span className="lbl" style={{ fontSize: 11, marginTop: 6 }}>
          {range.from === ""
            ? "Every hour is allowed."
            : range.from === range.to
              ? `Signals may fire in the ${hourLabel(Number(range.from))} hour only.`
              : `Signals may fire from ${hourLabel(Number(range.from))} through ${hourLabel(Number(range.to))} at bar close.`}
        </span>
        {range.custom && (
          <span className="lbl" style={{ fontSize: 11, marginTop: 4, color: "#d29922" }}>
            Custom hour set selected. Choosing a window replaces it.
          </span>
        )}
      </label>

      <label>
        <span className={r.label}>Days (UTC)</span>
        <details className={r.multi}>
          <summary className={r.input}>
            <span>{daysSummary(days)}</span>
            <span aria-hidden>▾</span>
          </summary>
          <div className={r.multiMenu}>
            <label className={r.multiRow}>
              <input
                type="checkbox"
                checked={days.length === 0}
                onChange={() => onDays([])}
              />
              <span>Every day</span>
            </label>
            {DAY_NAMES.map((label, d) => (
              <label key={label} className={r.multiRow}>
                <input
                  type="checkbox"
                  checked={days.includes(d)}
                  onChange={(e) => {
                    const next = e.target.checked
                      ? [...days, d]
                      : days.filter((x) => x !== d);
                    onDays([...new Set(next)].sort((a, b) => a - b));
                  }}
                />
                <span>{label}</span>
              </label>
            ))}
          </div>
        </details>
        <span className="lbl" style={{ fontSize: 11, marginTop: 6 }}>
          Weekdays are Monday through Friday. Every day is the default.
        </span>
      </label>

      <label>
        <span className={r.label}>Dates (UTC)</span>
        <div className={r.timeRow}>
          <input
            className={r.input}
            value={dateDraft}
            placeholder="2026-11-05 or 2026-11-05/2026-11-10"
            onChange={(e) => setDateDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addDate();
              }
            }}
          />
          <button type="button" className="lbl" style={{ whiteSpace: "nowrap" }}
            onClick={addDate}>
            + Add
          </button>
        </div>
        {dates.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
            {dates.map((d) => (
              <span key={d} style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
                padding: "3px 8px", fontSize: 12,
              }}>
                <span className="num">{d}</span>
                <button type="button" aria-label={`Remove ${d}`}
                  style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", padding: 0 }}
                  onClick={() => onDates(dates.filter((x) => x !== d))}>✕</button>
              </span>
            ))}
          </div>
        )}
        <span className="lbl" style={{ fontSize: 11, marginTop: 6 }}>
          A single ISO date or an inclusive range. Empty means every date.
        </span>
      </label>
    </div>
  );
}

// ---- main component ----


export default function Compose() {
  const nav = useNavigate();
  const { user, profile } = useAuth();
  const [sp, setSp] = useSearchParams();
  const botId = sp.get("bot");
  const startFamily = sp.get("family");
  const startCoin = sp.get("coin");
  const { data: bot, loading: botLoading } = useMyBot(botId);
  const { data: universes } = useUniverses();

  const [name, setName] = useState("");
  const [color, setColor] = useState(DEFAULT_BOT_COLOR);
  const [visibility, setVisibility] = useState<Visibility>("private");
  const [prompt, setPrompt] = useState(() => sp.get("prompt") ?? "");
  const [started, setStarted] = useState(() => Boolean(botId || startFamily));
  const [presetKey, setPresetKey] = useState<string>("blank");
  const [spec, setSpec] = useState<StrategySpec>(blankSpec("fleet-60"));
  const [seeded, setSeeded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [savedId, setSavedId] = useState<string | null>(botId);
  const [showUniModal, setShowUniModal] = useState(false);
  const creatingRef = useRef(false);

  // Custom universe: a hand-picked subset of the current market. Coins live in
  // local state while composing; the owned pf_universe is written at save time
  // so the backtest (by slug) and live (by universe_id) resolve the same set.
  const me = user?.id ?? null;
  const [customMode, setCustomMode] = useState(false);
  const [customCoins, setCustomCoins] = useState<string[]>([]);
  const [customName, setCustomName] = useState("");
  const [customSaved, setCustomSaved] = useState(false);
  const customUni = useRef<{ id: string; slug: string } | null>(null);
  const [coinQuery, setCoinQuery] = useState("");
  const assetClass = ASSET_CLASS(spec.market);
  const { data: coinList } = useCoins(assetClass);

  const universeList = universes ?? [];
  const marketUniverses = useMemo(
    () =>
      universeList.filter(
        (u) => u.market === assetClass && u.saved && (u.owner === null || u.owner === me),
      ),
    [universeList, assetClass, me],
  );
  const selectedUniverse =
    marketUniverses.find((u) => u.slug === spec.universe) ??
    universeList.find((u) => u.slug === spec.universe);
  const { data: universeDetail } = useUniverse(spec.universe || "fleet-60");
  const presetCoins = useMemo(
    () => (universeDetail?.pf_universe_coins ?? []).map((c) => c.coin_symbol),
    [universeDetail],
  );
  const uniCoins = customMode ? customCoins : presetCoins;
  const coinMatches = useMemo(() => {
    const q = coinQuery.trim().toUpperCase();
    const picked = new Set(customCoins);
    return (coinList ?? [])
      .filter((c) => !picked.has(c.symbol))
      .filter((c) => !q || c.symbol.includes(q) || (c.name ?? "").toUpperCase().includes(q))
      .slice(0, 40);
  }, [coinList, coinQuery, customCoins]);
  const marketMeta = CATALOG.markets.find((m) => m.id === spec.market);
  const familySlug = PRESETS.find((pr) => pr.key === presetKey)?.family ?? null;
  const backtestIssues = specIssues(spec, "backtest");
  const liveIssues = specIssues(spec, "live");
  const backtestBlockers = backtestIssues.filter((i) => i.blocking);
  const liveBlockers = liveIssues.filter((i) => i.blocking);
  const liveOnlyBlockers = liveBlockers.filter(
    (b) => !backtestBlockers.some((x) => x.id === b.id),
  );
  const warnings = backtestIssues.filter(
    (i) => !i.blocking && !liveOnlyBlockers.some((x) => x.id === i.id),
  );

  // seed
  useEffect(() => {
    if (seeded || botLoading) return;
    if (botId && !bot) return;
    if (bot) {
      setSavedId(bot.id);
      setName(bot.name);
      setColor(botColor(bot));
      setVisibility(bot.visibility ?? "private");
      const s = (bot.spec as StrategySpec | null) ?? null;
      if (s && s.entry) {
        const merged = { ...mergeSpec(blankSpec(s.universe ?? "fleet-60"), s), name: bot.name };
        // Legacy bots encoded a hand-picked set as a universe `only` filter.
        // Convert to the custom-universe model (the picked set IS the universe).
        const only = (merged.filters ?? []).find((f) => f.kind === "universe") as { only?: string[] } | undefined;
        if (only?.only?.length) {
          setCustomMode(true);
          setCustomCoins(only.only.map((x) => String(x).toUpperCase()));
          customUni.current = null;
          setSpec({ ...merged, universe: CUSTOM_UNI, filters: merged.filters.filter((f) => f.kind !== "universe") });
        } else {
          setSpec(merged);
        }
        const pk = PRESETS.find((pr) => pr.family === bot.family_slug && JSON.stringify(pr.spec.entry) === JSON.stringify(s.entry))?.key;
        setPresetKey(pk ?? "blank");
      } else {
        setSpec(blankSpec("fleet-60"));
      }
      setStarted(true);
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
    const base = PRESETS.find((pr) => pr.key === pk)?.spec ?? blankSpec("fleet-60");
    const initName = slug ? base.name : "";
    setName(initName);
    setVisibility(profile?.default_bot_visibility ?? "private");
    // Arriving from the Market page with ?coin=BTC: start a custom universe of
    // exactly that coin, so "Build a bot on X" trades X (backtest == live).
    if (startCoin) {
      setCustomMode(true);
      setCustomCoins([startCoin.toUpperCase()]);
      customUni.current = null;
    }
    const seedSpec: StrategySpec = startCoin
      ? { ...base, name: initName, universe: CUSTOM_UNI, filters: [] }
      : { ...base, name: initName };
    setSpec(seedSpec);
    if (slug || startCoin) setStarted(true);
    setSeeded(true);
  }, [bot, botId, botLoading, seeded, startFamily, startCoin]);

  // Assistant "Build" hands off via ?prompt= (plus a changing token) and we run
  // the SAME parser the manual box uses — the one path that actually works. The
  // token changes every click so this fires even when Compose is already mounted.
  const parseTok = sp.get("k");
  useEffect(() => {
    const pr = (sp.get("prompt") || "").trim();
    if (!parseTok || !pr) return;
    runParse(pr);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parseTok]);

  // An existing bot whose universe is an owned, unsaved (throwaway) universe is
  // edited inline as a custom selection — not shown as a dropdown preset.
  useEffect(() => {
    if (!seeded || customMode || !me) return;
    const u = universeList.find((x) => x.slug === spec.universe);
    if (u && u.owner === me && !u.saved) {
      customUni.current = { id: u.id, slug: u.slug };
      setCustomName(u.name === "Custom universe" ? "" : u.name);
      setCustomSaved(false);
      setCustomMode(true);
    }
  }, [seeded, customMode, me, universeList, spec.universe]);

  // Load that universe's coins once they resolve (existing custom only).
  useEffect(() => {
    if (customMode && customUni.current && customCoins.length === 0 && presetCoins.length) {
      setCustomCoins(presetCoins);
    }
  }, [customMode, customCoins.length, presetCoins]);

  const persistSilently = async (): Promise<string | null> => {
    if (!user || !seeded) return savedId;
    const finalName = name.trim() || "New bot";
    const u = await resolveUniverse();
    const finalSpec: StrategySpec = { ...spec, name: finalName, universe: u.slug };
    const direction = finalSpec.side === "long" ? "long" : finalSpec.side === "short" ? "short" : "both";
    const input = {
      name: finalName,
      family_slug: familySlug,
      universe_id: u.id,
      direction,
      params: { ...(bot?.params ?? {}), color },
      spec: toWireSpec(finalSpec),
      visibility,
    };
    const currentId = savedId ?? bot?.id ?? null;
    if (currentId) {
      await autosaveBot({ id: currentId, ...input });
      return currentId;
    }
    if (creatingRef.current) return null;
    creatingRef.current = true;
    try {
      let candidate = finalName;
      for (let n = 2; n <= 50; n++) {
        const check = await botNameTaken(user.id, candidate);
        if (!check.taken) break;
        candidate = `${finalName} ${n}`;
      }
      const { data } = await createDraftBot({
        owner: user.id,
        ...input,
        name: candidate,
        spec: { ...toWireSpec(finalSpec), name: candidate },
      });
      if (data?.id) {
        setSavedId(data.id);
        setName((cur) => (cur === finalName || !cur.trim() ? candidate : cur));
        setSp({ bot: data.id }, { replace: true });
        return data.id;
      }
    } finally {
      creatingRef.current = false;
    }
    return null;
  };

  // Silent debounced auto-save whenever setup changes (incl. a custom universe).
  useEffect(() => {
    if (!seeded || !started || !user) return;
    const t = setTimeout(() => {
      void persistSilently();
    }, 500);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, color, visibility, spec, familySlug, seeded, started, user, customMode, customCoins, customName, customSaved]);

  // ensure universe list loaded -> default slug for current market (not in custom mode)
  useEffect(() => {
    if (!seeded || customMode) return;
    if (marketUniverses.length && !marketUniverses.find((u) => u.slug === spec.universe)) {
      setSpec((s) => ({ ...s, universe: marketUniverses[0].slug }));
    }
  }, [marketUniverses, seeded, spec.universe, customMode]);

  const setParam = (path: string, value: unknown) =>
    setSpec((s) => setPath(s, path, value));

  // Which book the two-sided editor is editing (long/short). Ignored unless
  // side === "both". Seed the short book the first time a bot goes two-sided.
  const [dir, setDir] = useState<"long" | "short">("long");
  useEffect(() => {
    if (spec.side === "both" && (!spec.entry_short || !spec.exit_short)) {
      setSpec((s) => ({
        ...s,
        entry_short: s.entry_short ?? { logic: "AND", children: [] },
        exit_short: s.exit_short ?? JSON.parse(JSON.stringify(s.exit)),
      }));
    }
  }, [spec.side, spec.entry_short, spec.exit_short]);

  const clearIssue = (issue: { id: string; path: string }) => {
    if (issue.id === "stop.trail") setParam("exit.stop.mode", "none");
    else setParam(issue.path, undefined);
  };

  // Two-sided editing: when on the short book, exit controls read/write the
  // short exit. ParamControl keys off "exit.*", so we hand it a spec whose
  // `exit` IS the short exit and rewrite the write path to "exit_short.*".
  const isBoth = spec.side === "both";
  const shortExit = isBoth && dir === "short";
  const exitViewSpec = shortExit
    ? ({ ...spec, exit: spec.exit_short ?? spec.exit } as StrategySpec)
    : spec;
  const exitChange = shortExit
    ? (path: string, val: unknown) =>
        setParam(path.replace(/^exit(?=\.|$)/, "exit_short"), val)
    : setParam;
  const setActiveExit = (updater: (ex: ExitCfg) => ExitCfg) =>
    setSpec((s) =>
      s.side === "both" && dir === "short"
        ? { ...s, exit_short: updater(s.exit_short ?? s.exit) }
        : { ...s, exit: updater(s.exit) });

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

  // --- custom universe (hand-picked subset of the market) ---
  const enterCustom = () => {
    setCustomCoins((cur) => (cur.length ? cur : presetCoins));
    setCustomMode(true);
    // drop any legacy universe filter — the picked set *is* the universe now
    setSpec((s) => ({ ...s, universe: CUSTOM_UNI, filters: s.filters.filter((f) => f.kind !== "universe") }));
  };
  const exitCustom = (slug: string) => {
    customUni.current = null;
    setCustomMode(false);
    setCustomCoins([]);
    setCustomName("");
    setCustomSaved(false);
    setSpec((s) => ({ ...s, universe: slug }));
  };
  const addCoin = (sym: string) => {
    setCustomCoins((c) => (c.includes(sym) ? c : [...c, sym]));
    setCoinQuery("");
  };
  const removeCoin = (sym: string) => setCustomCoins((c) => c.filter((x) => x !== sym));

  const ensureCustomUniverse = async (): Promise<{ id: string; slug: string } | null> => {
    if (!user) return null;
    if (customUni.current) {
      const ok = await updateUniverse(customUni.current.id, {
        name: customName, saved: customSaved, market: assetClass, coins: customCoins,
      });
      return ok ? customUni.current : null;
    }
    const created = await createUniverse({
      owner: user.id, name: customName, market: assetClass, coins: customCoins, saved: customSaved,
    });
    if (created) customUni.current = created;
    return created;
  };

  // The universe (slug + id) to persist. In custom mode this writes/updates the
  // owned pf_universe so the backtest and live both resolve the picked set.
  const resolveUniverse = async (): Promise<{ slug: string; id: string | null }> => {
    if (customMode && customCoins.length && user) {
      const cu = await ensureCustomUniverse();
      if (cu) return { slug: cu.slug, id: cu.id };
    }
    const found = universeList.find((u) => u.slug === spec.universe);
    return { slug: spec.universe, id: found?.id ?? bot?.universe_id ?? null };
  };

  const loadPreset = (key: string) => {
    setPresetKey(key);
    const pr = PRESETS.find((p) => p.key === key);
    setSpec((s) => {
      const base = blankSpec(s.universe || "fleet-60");
      if (!pr || key === "blank") return { ...base, name: name || "New bot" };
      return { ...mergeSpec(base, pr.spec), name: name || pr.spec.name };
    });
  };

  // Apply a parse-strategy / assistant spec (same JSON schema either way) to the
  // Builder. Used by the NL "Parse & build" button AND the assistant's structured
  // hand-off, so every field the conversation settled (timing, exits, days) lands
  // exactly — no re-parse, no re-guess. Named instruments become a custom universe.
  const applyParsedSpec = (cspec: Partial<StrategySpec> & Record<string, any>) => {
    const defaultUni = cspec.market === "equity" ? "mag-7" : "fleet-60";
    const next = blankSpec(defaultUni);
    next.name = typeof cspec.name === "string" && cspec.name.trim() ? cspec.name.trim() : name || "New bot";
    setName(next.name);
    next.side = cspec.side === "long" || cspec.side === "short" ? cspec.side : "short";
    next.market =
      typeof cspec.market === "string" && CATALOG.markets.some((m) => m.id === cspec.market) ? cspec.market : "crypto_perp";
    next.universe =
      typeof cspec.universe === "string" && cspec.universe.trim()
        ? cspec.universe.trim()
        : next.market === "equity" ? "mag-7" : "fleet-60";
    next.timeframe = typeof cspec.timeframe === "string" && cspec.timeframe.trim() ? cspec.timeframe.trim() : "15m";
    next.fresh = typeof cspec.fresh === "boolean" ? cspec.fresh : false;
    next.entry = normGroup(cspec.entry);
    if (cspec.timing && typeof cspec.timing === "object") {
      const uniq = (xs: number[]) => Array.from(new Set(xs));
      const hrs = Array.isArray(cspec.timing.hours_utc)
        ? uniq(cspec.timing.hours_utc.map(Number).filter((n: number) => Number.isInteger(n) && n >= 0 && n <= 23))
        : [];
      const dys = Array.isArray(cspec.timing.days_utc)
        ? uniq(cspec.timing.days_utc.map(Number).filter((n: number) => Number.isInteger(n) && n >= 0 && n <= 6))
        : [];
      next.timing = { hours_utc: hrs.length >= 24 ? [] : hrs, days_utc: dys.length >= 7 ? [] : dys };
    }
    if (cspec.exit && typeof cspec.exit === "object") {
      const baseExit = blankSpec(defaultUni).exit;
      const stopRaw = cspec.exit.stop;
      const stopMode =
        stopRaw && typeof stopRaw === "object" && ["none", "hh", "dstop", "sig"].includes(stopRaw.mode) ? stopRaw.mode : "none";
      next.exit = {
        ...baseExit,
        time_bars: typeof cspec.exit.time_bars === "number" && cspec.exit.time_bars >= 1 ? Math.round(cspec.exit.time_bars) : baseExit.time_bars,
        stop: {
          mode: stopMode,
          window: typeof stopRaw?.window === "number" && stopRaw.window >= 1 ? Math.round(stopRaw.window) : 16,
          param: typeof stopRaw?.param === "number" ? stopRaw.param : 0,
        },
        ...(typeof cspec.exit.take_profit === "number" && cspec.exit.take_profit > 0 ? { take_profit: cspec.exit.take_profit } : {}),
      };
    }
    if (cspec.sizing && typeof cspec.sizing === "object") {
      const baseSizing = blankSpec(defaultUni).sizing;
      next.sizing = {
        risk: typeof cspec.sizing.risk === "number" ? cspec.sizing.risk : baseSizing.risk,
        notional_cap: typeof cspec.sizing.notional_cap === "number" ? cspec.sizing.notional_cap : baseSizing.notional_cap,
        weight: typeof cspec.sizing.weight === "number" ? cspec.sizing.weight : baseSizing.weight,
      };
    }
    next.filters = Array.isArray(cspec.filters) ? cspec.filters : [];

    const onlyFilter = (next.filters as Array<{ kind?: string; only?: string[] }>).find((f) => f?.kind === "universe")?.only;
    const picked = Array.from(
      new Set(
        [...(Array.isArray(cspec.coins) ? cspec.coins : []), ...(Array.isArray(onlyFilter) ? onlyFilter : [])]
          .map((x) => String(x).toUpperCase().trim())
          .filter(Boolean),
      ),
    );
    customUni.current = null;
    if (picked.length) {
      setCustomMode(true);
      setCustomCoins(picked);
      next.universe = CUSTOM_UNI;
      next.filters = next.filters.filter((f) => (f as { kind?: string }).kind !== "universe");
    } else {
      setCustomMode(false);
      setCustomCoins([]);
    }
    setSpec(next);
    setPresetKey("blank");
    setStarted(true);
    setErr(null);
  };

  // The one path that works: send text to the parser and apply the result. Used
  // by the "Parse & build" box AND the assistant's Build button (via ?prompt=).
  const runParse = (text: string) => {
    setParsing(true);
    setErr(null);
    fetch(
      `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/parse-strategy?text=${encodeURIComponent(text)}`,
      { headers: { apikey: import.meta.env.VITE_SUPABASE_KEY } },
    )
      .then((r) => r.json())
      .then((data) => {
        setParsing(false);
        if (data.error || !data.spec || data.spec._parseError) {
          setSpec(blankSpec("fleet-60"));
          setPresetKey("blank");
          setStarted(true);
          setErr(data.error || data.spec?._parseError || "Could not parse strategy");
          return;
        }
        applyParsedSpec(data.spec as Partial<StrategySpec> & Record<string, any>);
      })
      .catch(() => {
        setParsing(false);
        setSpec(blankSpec("fleet-60"));
        setPresetKey("blank");
        setStarted(true);
        setErr("Could not reach parsing service");
      });
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
    let entryErr = validateEntry(spec.entry);
    if (entryErr && spec.side === "both") entryErr = `Long book — ${entryErr}`;
    if (!entryErr && spec.side === "both") {
      const se = validateEntry(spec.entry_short ?? { logic: "AND", children: [] });
      if (se) entryErr = `Short book — ${se}`;
    }
  if (toTraining && entryErr) {
      setErr(entryErr);
      return;
    }
    if (toTraining && (!Number.isFinite(spec.exit.time_bars) || spec.exit.time_bars < 1)) {
      setErr("Max hold must be at least 1 bar.");
      return;
    }
    if (toTraining) {
      const blockers = blockingIssues(spec, "backtest");
      if (blockers.length) {
        setErr(`${blockers[0].label}: ${blockers[0].reason}`);
        return;
      }
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
    if (toTraining && customMode && customCoins.length === 0) {
      setSaving(false);
      setErr("Add at least one token to your custom universe.");
      return;
    }

    const u = await resolveUniverse();
    const finalSpec: StrategySpec = { ...spec, name: finalName, universe: u.slug };
    const direction = finalSpec.side === "long" ? "long" : finalSpec.side === "short" ? "short" : "both";
    const input = {
      name: finalName,
      family_slug: familySlug,
      universe_id: u.id,
      direction,
      params: { ...(bot?.params ?? {}), color },
      spec: toWireSpec(finalSpec),
      visibility,
    };

    let id = savedId ?? bot?.id ?? null;
    if (id) {
      // Preserve the setup this edit is about to overwrite as a version, so the
      // prior (possibly deployed) strategy keeps its own row in the history.
      if (bot?.spec) await saveBotVersion(id, bot.spec as Record<string, unknown>);
      const { error } = await updateDraftBot({ id, ...input });
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
      setSavedId(id);
    }
    // Snapshot the setup just saved (deduped by fingerprint, so an unchanged
    // re-save is a no-op). This is the row that becomes the bot's current version.
    if (id) await saveBotVersion(id, input.spec);

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
      universe_id: u.id,
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

  if (botLoading && !savedId) return <StepLoading step={1} />;
  if (botId && !bot && !savedId) return <MissingBot step={1} />;

  const strategyPreviewRows = buildStrategyRows(
    spec as unknown as Record<string, unknown>,
    { color },
    spec.side,
    bot?.condition_filter,
  );
  const shortCoins = uniCoins.slice(0, 8);
  const moreCoins = Math.max(0, uniCoins.length - shortCoins.length);

  const handleStepNav = async (targetPath: string) => {
    const id = await persistSilently();
    const base = targetPath.split("?")[0];
    nav(withBot(base, id ?? savedId ?? botId));
  };

  return (
    <>
      <BackBar to="/build" label="Build" />
      <Steps current={1} onNavigate={(target) => void handleStepNav(target)} />
       <div className={p.body}>
        <div className="lbl" style={{ fontSize: 12, marginBottom: 16 }}>
          <Req /> required — everything else has a sensible default you can tune.
        </div>
        {/* Identity — always first */}
        <div style={{ paddingBottom: 28, borderBottom: "1px solid var(--line)", display: "flex", gap: 24, alignItems: "center", flexWrap: "wrap", marginBottom: 28 }}>
          <svg width="56" height="56" viewBox="0 0 56 56" style={{ flex: "none" }}>
            <rect width="56" height="56" rx="28" fill="#12161D" />
            <path d={identicon(name || "bot", 36)} fill={color} transform="translate(10 10)" />
          </svg>
          <div style={{ flex: "1 1 260px", minWidth: 0 }}>
            <div className={r.label}>Bot name <Req /></div>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Name this bot"
              style={{ background: "transparent", border: "none", color: "var(--fg)", fontSize: 32, fontWeight: 500, letterSpacing: "-0.02em", width: "100%", marginTop: 6, outline: "none" }}
            />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <span className={r.label}>Color</span>
            <div className={r.swatchRows}>
              {FLEET_PALETTE.map((hue) => (
                <div key={hue.name} className={r.swatchRow} title={hue.name}>
                  {hue.shades.map((c, i) => (
                    <button
                      key={c}
                      type="button"
                      className={`${r.swatch} ${color === c ? r.swatchOn : ""}`}
                      style={{ background: c }}
                      onClick={() => setColor(c)}
                      aria-label={`${hue.name} ${[100, 200, 300, 400, 500][i]}`}
                      aria-pressed={color === c}
                      title={`${hue.name} ${[100, 200, 300, 400, 500][i]} · ${c}`}
                    />
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>

        {!started && (
          <section style={{ maxWidth: 720, padding: "0 0 48px" }}>
            <h1 className={p.title} style={{ fontSize: 34 }}>Compose your bot's strategy</h1>
            <div className={p.subtitle} style={{ marginTop: 8 }}>
              Describe the strategy you want in plain English. We'll parse it into rules you can refine.
            </div>
            <div style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 12 }}>
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
                  disabled={parsing}
                  onClick={() => {
                    const text = (prompt || name).trim();
                    if (!text) {
                      setErr("Describe the strategy you want to parse.");
                      return;
                    }
                    runParse(text);
                  }}
                >
                  {parsing ? "Parsing…" : "Parse & build"}
                </button>
                <button
                  className={p.btn}
                  style={{ height: 46 }}
                  onClick={() => {
                    setSpec(blankSpec("fleet-60"));
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
          <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
            <button className={p.btn} style={{ height: 36, fontSize: 13 }} onClick={() => setStarted(false)}>← Back to parse</button>
          </div>
        )}
        {started && (

        <section style={{ display: "flex", flexWrap: "wrap", gap: 32, paddingTop: 28, alignItems: "flex-start" }}>
           <div style={{ flex: "999 1 620px", minWidth: 0 }}>
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
              <h2 className={r.h2}>Market &amp; universe <Req /></h2>
              <div style={{ color: "var(--muted)", fontSize: 13, marginTop: 4 }}>
                A universe is a subset of a market — pick a ready-made one or build your own.
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 14, marginTop: 12 }}>
                <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <span className={r.label}>Market</span>
                  <select
                    className={r.input}
                    value={spec.market}
                    onChange={(e) => {
                      const nextMarket = e.target.value;
                      const first = universeList.find(
                        (u) => u.market === ASSET_CLASS(nextMarket) && u.saved && (u.owner === null || u.owner === me),
                      );
                      // A universe belongs to exactly one market — never carry
                      // the previous market's universe across a switch. Use an
                      // in-market saved one if present, else drop into custom
                      // build mode so the picker offers only the new market's
                      // instruments (stops e.g. an fx bot inheriting fleet-60).
                      customUni.current = null;
                      setCustomMode(!first);
                      setCustomCoins([]);
                      setCustomName("");
                      setCustomSaved(false);
                      setSpec((s) => ({
                        ...s,
                        market: nextMarket,
                        universe: first?.slug ?? CUSTOM_UNI,
                        filters: s.filters.filter((f) => f.kind !== "universe"),
                      }));
                    }}
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
                    value={customMode ? CUSTOM_UNI : spec.universe}
                    onChange={(e) => {
                      const v = e.target.value;
                      if (v === CUSTOM_UNI) enterCustom();
                      else exitCustom(v);
                    }}
                  >
                    {marketUniverses.map((u) => (
                      <option key={u.id} value={u.slug}>
                        {u.name ?? u.slug}
                      </option>
                    ))}
                    <option value={CUSTOM_UNI}>Custom — pick tokens…</option>
                  </select>
                  <span className="lbl">
                    {customMode
                      ? `${customCoins.length} token${customCoins.length === 1 ? "" : "s"} picked`
                      : (selectedUniverse?.description ?? "")}
                  </span>
                </label>
                <ParamControl spec={spec} path="timeframe" onChange={setParam} />
              </div>

              {customMode && (
                <div className={r.uniPicker}>
                  <input
                    className={r.input}
                    placeholder={`Search ${spec.market === "equity" ? "stocks" : "coins"} to add…`}
                    value={coinQuery}
                    onChange={(e) => setCoinQuery(e.target.value)}
                  />
                  {coinQuery.trim() && (
                    <div className={r.coinResults}>
                      {coinMatches.length === 0 ? (
                        <div className="lbl" style={{ padding: "8px 10px" }}>No matches.</div>
                      ) : (
                        coinMatches.map((c) => (
                          <button type="button" key={c.symbol} className={r.coinOpt} onClick={() => addCoin(c.symbol)}>
                            <span className="num">{c.symbol}</span>
                            {c.name && <span className="lbl">{c.name}</span>}
                          </button>
                        ))
                      )}
                    </div>
                  )}
                  {customCoins.length > 0 ? (
                    <div className={r.chips}>
                      {customCoins.map((c) => (
                        <button type="button" key={c} className={r.chip} onClick={() => removeCoin(c)} title="Remove">
                          {c} <span aria-hidden>×</span>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="lbl" style={{ marginTop: 8 }}>No tokens yet — search above and click to add.</div>
                  )}
                  <label className={r.saveUni}>
                    <input type="checkbox" checked={customSaved} onChange={(e) => setCustomSaved(e.target.checked)} />
                    <span>Save this universe for reuse</span>
                  </label>
                  {customSaved && (
                    <input
                      className={r.input}
                      placeholder="Universe name (e.g. My majors)"
                      value={customName}
                      onChange={(e) => setCustomName(e.target.value)}
                    />
                  )}
                </div>
              )}
            </div>

            {/* Direction / fresh / sizing */}
            <div className={r.formRow}>
              <h2 className={r.h2}>{groupLabel("direction")} &amp; {groupLabel("sizing")}</h2>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))", gap: 14, marginTop: 12 }}>
                {paramsForGroup("direction").map((p) => (
                  <ParamControl key={p.key} spec={spec} path={p.key} onChange={setParam} />
                ))}
                {paramsForGroup("sizing")
                  .filter((p) => p.status !== "ignored")
                  .map((p) => (
                    <ParamControl key={p.key} spec={spec} path={p.key} onChange={setParam} />
                  ))}
              </div>
              {spec.sizing.weight !== undefined && spec.sizing.weight !== 1 && (
                <div className="lbl" style={{ marginTop: 10, color: "#d29922" }}>
                  Portfolio weight is stored but this single-bot engine does not
                  read it, so it cannot change results.
                </div>
              )}
            </div>

            {/* Entry conditions */}
            <div className={r.formRow}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <h2 className={r.h2}>
                  {groupLabel("entry")} conditions <Req />
                  {isBoth && <span className="lbl"> · {dir === "short" ? "short" : "long"} book</span>}
                </h2>
                <span className="lbl">
                  {(isBoth && dir === "short"
                    ? spec.entry_short?.children.length ?? 0
                    : spec.entry.children.length)} top-level
                </span>
              </div>
              <div className={r.label} style={{ margin: "4px 0 12px" }}>
                {isBoth
                  ? "Two-sided bot: compose the long and short books separately. When flat, whichever fires opens; if both fire, the bar is skipped."
                  : "Compose the condition tree. Indicators available depend on the market."}
              </div>
              <div style={{ maxWidth: 240, marginBottom: 14 }}>
                <ParamControl spec={spec} path="fresh" onChange={setParam} />
              </div>
              {isBoth && <DirTabs dir={dir} onDir={setDir} />}
              <NodeEditor
                node={isBoth && dir === "short"
                  ? (spec.entry_short ?? { logic: "AND", children: [] })
                  : spec.entry}
                market={spec.market}
                onChange={(n) => setSpec((s) =>
                  s.side === "both" && dir === "short"
                    ? { ...s, entry_short: n as CondGroup }
                    : { ...s, entry: n as CondGroup })}
                onRemove={() => {}}
              />
            </div>

            {/* Timing */}
            <div className={r.formRow}>
              <h2 className={r.h2}>{groupLabel("timing")} (UTC) <Opt /></h2>
              <div className={r.label} style={{ margin: "4px 0 12px" }}>
                Optional entry windows, measured at bar close. Leave the window
                clear and every day selected to trade around the clock.
              </div>
              <TimingControl
                hours={spec.timing?.hours_utc ?? []}
                days={spec.timing?.days_utc ?? []}
                dates={spec.timing?.dates ?? []}
                onHours={(hours) =>
                  setSpec((s) => ({ ...s, timing: { ...s.timing, hours_utc: hours } }))
                }
                onDays={(days) =>
                  setSpec((s) => ({ ...s, timing: { ...s.timing, days_utc: days } }))
                }
                onDates={(dates) =>
                  setSpec((s) => ({ ...s, timing: { ...s.timing, dates } }))
                }
              />
            </div>

            {/* Exit */}
            <div className={r.formRow}>
              <h2 className={r.h2}>
                {groupLabel("exit")}
                {isBoth && <span className="lbl"> · {dir === "short" ? "short" : "long"} book</span>}
              </h2>
              {isBoth && <div style={{ marginTop: 10 }}><DirTabs dir={dir} onDir={setDir} /></div>}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 14, marginTop: 12 }}>
                {paramsForGroup("exit")
                  .filter((p) => p.kind !== "condition" && p.status !== "unsupported")
                  .filter((p) => !EXIT_CUSTOM.has(p.key))
                  .map((p) => (
                    <ParamControl key={p.key} spec={exitViewSpec} path={p.key} onChange={exitChange} />
                  ))}
              </div>
              <div style={{ marginTop: 16, paddingTop: 14, borderTop: "1px solid var(--line)" }}>
                <label style={{ display: "flex", alignItems: "center", gap: 9 }}>
                  <input
                    type="checkbox"
                    checked={Boolean(exitViewSpec.exit.trailing)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        const k = specParam("exit.trailing.k")?.default ?? 3;
                        const natr = specParam("exit.trailing.natr")?.default ?? 24;
                        exitChange("exit.trailing", { k, natr });
                      } else {
                        exitChange("exit.trailing", undefined);
                      }
                    }}
                  />
                  <span className="lbl">Trailing stop <Opt /></span>
                </label>
                {exitViewSpec.exit.trailing && (
                  <>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 14, marginTop: 12 }}>
                      <ParamControl spec={exitViewSpec} path="exit.trailing.k" onChange={exitChange} showNote={false} />
                      <ParamControl spec={exitViewSpec} path="exit.trailing.natr" onChange={exitChange} showNote={false} />
                    </div>
                    <div className="lbl" style={{ marginTop: 8, fontSize: 11 }}>
                      Ratchets a stop {exitViewSpec.exit.trailing?.k ?? 3}× the NATR behind
                      the best price since entry.
                    </div>
                  </>
                )}
              </div>
              {/* Exit conditions — a discretionary exit tree */}
              <div style={{ marginTop: 16, paddingTop: 14, borderTop: "1px solid var(--line)" }}>
                <label style={{ display: "flex", alignItems: "center", gap: 9 }}>
                  <input
                    type="checkbox"
                    checked={Boolean(exitViewSpec.exit.exit_conditions)}
                    onChange={(e) =>
                      setActiveExit((ex) => ({
                        ...ex,
                        exit_conditions: e.target.checked
                          ? { logic: "AND", children: [] }
                          : undefined,
                      }))
                    }
                  />
                  <span className="lbl">Exit conditions <Opt /></span>
                </label>
                <div className="lbl" style={{ fontSize: 11, marginTop: 4 }}>
                  Close the position on the bar this tree first fires — after the
                  stop and take-profit have had their say.
                </div>
                {exitViewSpec.exit.exit_conditions && (
                  <div style={{ marginTop: 12 }}>
                    <NodeEditor
                      node={exitViewSpec.exit.exit_conditions}
                      market={spec.market}
                      onChange={(n) =>
                        setActiveExit((ex) => ({ ...ex, exit_conditions: n as CondGroup }))
                      }
                      onRemove={() => {}}
                    />
                  </div>
                )}
              </div>
            </div>

            {/* Filters */}
            <div className={r.formRow}>
              <h2 className={r.h2}>Filters <Opt /></h2>
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
                      value={Number((((filterVal("regime_veto", "threshold") as number) ?? 0) * 100).toFixed(4))}
                      onChange={(e) =>
                        setSpec((s) => ({
                          ...s,
                          filters: s.filters.map((f) =>
                            f.kind === "regime_veto" ? { ...f, threshold: Number(e.target.value) / 100 } : f,
                          ),
                        }))
                      }
                      style={{ width: 100 }}
                    />
                  )}
                </label>
                {spec.filters.length > 0 && (
                  <div className="lbl" style={{ color: "#d29922" }}>
                    These are live gates. The backtest is unfiltered, so read its
                    numbers as the strategy before filters.
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Sticky Checkout / Strategy Sidebar */}
          <div
            style={{
              flex: "1 1 340px",
              minWidth: 0,
              display: "flex",
              flexDirection: "column",
              gap: 16,
              paddingTop: 4,
              position: "sticky",
              top: 24,
              alignSelf: "flex-start",
              maxHeight: "calc(100vh - 48px)",
              overflowY: "auto",
            }}
          >
            <div className="card" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, paddingBottom: 8, borderBottom: "1px solid var(--line)" }}>
                <svg width="34" height="34" viewBox="0 0 34 34" style={{ flex: "none" }}>
                  <rect width="34" height="34" rx="17" fill="#12161D" />
                  <path d={identicon(name.trim() || "New bot", 22)} fill={color} transform="translate(6 6)" />
                </svg>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 16, fontWeight: 500 }}>{name.trim() || "New bot"}</div>
                  <div className="lbl" style={{ marginTop: 2 }}>
                    {familySlug ?? "Custom"} · {spec.side} · {spec.market}
                  </div>
                </div>
              </div>

              {strategyPreviewRows.map(([k, val]) => (
                <div className={r.blk} key={k} style={{ padding: "8px 12px" }}>
                  <span className={r.tag}>{k}</span>
                  <span className="num" style={{ fontWeight: 400, fontSize: 12, lineHeight: 1.45, wordBreak: "break-word" }}>
                    {val}
                  </span>
                </div>
              ))}

              <div className={r.blk} style={{ padding: "10px 12px", flexDirection: "column", gap: 6 }}>
                <div style={{ display: "flex", justifyContent: "space-between", width: "100%", alignItems: "baseline" }}>
                  <span className={r.tag} style={{ width: "auto" }}>
                    Universe · {selectedUniverse?.name ?? spec.universe}
                  </span>
                  <span className="num lbl">{uniCoins.length} coins</span>
                </div>
                {uniCoins.length > 0 && (
                  <div className="num muted" style={{ fontSize: 12, lineHeight: 1.5 }}>
                    {shortCoins.join(", ")}
                    {moreCoins > 0 && (
                      <>
                        {" "}
                        <span
                          className="lk"
                          style={{ color: "#8BB4E8", fontWeight: 500 }}
                          onClick={() => setShowUniModal(true)}
                        >
                          +{moreCoins} more
                        </span>
                      </>
                    )}
                  </div>
                )}
                {uniCoins.length > 0 && (
                  <button
                    type="button"
                    className="lk lbl"
                    style={{
                      background: "none",
                      border: "none",
                      padding: 0,
                      color: "#8BB4E8",
                      textAlign: "left",
                      cursor: "pointer",
                      marginTop: 2,
                    }}
                    onClick={() => setShowUniModal(true)}
                  >
                    View all {uniCoins.length} coins →
                  </button>
                )}
              </div>
            </div>

            <div className="card" style={{ padding: 20 }}>
              <div className={r.label}>Engine coverage</div>
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 10, fontSize: 13 }}>
                <span>Backtest</span>
                <span style={{ color: backtestBlockers.length ? "var(--down)" : "var(--up)" }}>
                  {backtestBlockers.length ? "blocked" : "ready"}
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6, fontSize: 13 }}>
                <span>Live</span>
                <span style={{ color: liveBlockers.length ? "#d29922" : "var(--up)" }}>
                  {liveBlockers.length ? "needs pinning" : "ready"}
                </span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 12 }}>
                {backtestBlockers.map((i) => (
                  <div key={i.id} style={{ fontSize: 11, lineHeight: 1.4, color: "var(--down)" }}>
                    <b>{i.label}</b>
                    <div style={{ color: "var(--muted)" }}>{i.reason}</div>
                    <button
                      className={p.btn}
                      style={{ height: 24, padding: "0 8px", fontSize: 11, marginTop: 5 }}
                      onClick={() => clearIssue(i)}
                    >
                      Resolve
                    </button>
                  </div>
                ))}
                {liveOnlyBlockers.map((i) => (
                  <div key={i.id} style={{ fontSize: 11, lineHeight: 1.4, color: "#d29922" }}>
                    <b>Live: {i.label}</b>
                    <div style={{ color: "var(--muted)" }}>{i.reason}</div>
                    <button
                      className={p.btn}
                      style={{ height: 24, padding: "0 8px", fontSize: 11, marginTop: 5 }}
                      onClick={() => clearIssue(i)}
                    >
                      Remove
                    </button>
                  </div>
                ))}
                {warnings.map((i) => (
                  <div key={i.id} style={{ fontSize: 11, lineHeight: 1.4, color: "#d29922" }}>
                    <b>{i.label}</b>
                    <div style={{ color: "var(--muted)" }}>{i.reason}</div>
                  </div>
                ))}
                {!backtestBlockers.length && !liveBlockers.length && !warnings.length && (
                  <div className="lbl">Every selected feature is executable by both engines.</div>
                )}
              </div>
            </div>

            <button
              className={`${p.btn} ${p.pri}`}
              style={{ height: 48, fontSize: 14, justifyContent: "center" }}
              disabled={saving || backtestBlockers.length > 0}
              title={backtestBlockers[0]?.reason}
              onClick={() => save(true)}
            >
              {saving ? "Starting…" : "Start training →"}
            </button>
            {(savedId || botId) && (
              <button
                className={p.btn}
                style={{ height: 42, justifyContent: "center" }}
                onClick={() => void handleStepNav("/build/training")}
              >
                Continue to training →
              </button>
            )}
            {!user && <div className="lbl">Log in to save this strategy to your roster.</div>}
            {err && <div style={{ color: "var(--down, #ff5c6c)", fontSize: 13 }}>{err}</div>}
          </div>
        </section>
        )}

        {showUniModal && (
          <div
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(1, 4, 9, 0.72)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 70,
              padding: 20,
            }}
            onClick={(e) => e.target === e.currentTarget && setShowUniModal(false)}
          >
            <div
              className="card"
              style={{
                width: "min(640px, 94vw)",
                maxHeight: "80vh",
                display: "flex",
                flexDirection: "column",
                padding: "20px 22px",
                gap: 14,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                <div>
                  <div style={{ fontSize: 18, fontWeight: 500 }}>
                    {selectedUniverse?.name ?? spec.universe}{" "}
                    <span className="num muted" style={{ fontSize: 14, fontWeight: 400 }}>
                      ({uniCoins.length} coins)
                    </span>
                  </div>
                  {selectedUniverse?.description && (
                    <div className="lbl" style={{ marginTop: 4 }}>{selectedUniverse.description}</div>
                  )}
                </div>
                <button
                  type="button"
                  className={p.btn}
                  style={{ height: 32, padding: "0 10px" }}
                  onClick={() => setShowUniModal(false)}
                >
                  ✕
                </button>
              </div>
              <div
                style={{
                  overflowY: "auto",
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(92px, 1fr))",
                  gap: 8,
                  paddingTop: 6,
                }}
              >
                {uniCoins.map((c) => (
                  <div
                    key={c}
                    className="num"
                    style={{
                      padding: "8px 10px",
                      borderRadius: 8,
                      background: "#0f1319",
                      border: "1px solid var(--line-2)",
                      fontSize: 12,
                      textAlign: "center",
                    }}
                  >
                    {c}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
