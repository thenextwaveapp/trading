import catalog from "../data/catalog.json";

export interface CatalogParam {
  name: string;
  type: string;
  default: unknown;
  min: number | null;
  max: number | null;
}

export interface CatalogIndicator {
  id: string;
  label: string;
  category: string;
  inputs: string[];
  params: CatalogParam[];
}

export interface CatalogMarket {
  id: string;
  label: string;
  provides: string[];
  series_kind: string;
  asset_class: string;
}

export interface SpecOption {
  value: string;
  label: string;
  backtest: boolean;
  live: boolean;
  status: "ok" | "partial" | "ignored" | "unsupported";
  reason: string;
}

export interface SpecVisibleIf {
  path: string;
  exists?: boolean;
  in?: unknown[];
  equals?: unknown;
}

export interface SpecParam {
  key: string;
  label: string;
  kind: "int" | "float" | "bool" | "enum" | "int_list" | "string" | "condition";
  default: unknown;
  group: string;
  help: string;
  min: number | null;
  max: number | null;
  step: number | null;
  unit: string | null;
  percent: boolean;
  choices: unknown[];
  options: SpecOption[];
  visible_if: SpecVisibleIf | null;
  status: "ok" | "partial" | "ignored" | "unsupported";
  backtest: boolean;
  live: boolean;
  sweep: boolean;
  in_default: boolean;
  reason: string;
}

export interface SpecFeature {
  id: string;
  label: string;
  path: string;
  op: "eq" | "neq" | "exists" | "nonempty" | "in";
  value?: unknown;
  values?: unknown[];
  backtest: boolean;
  live: boolean;
  status: "ok" | "partial" | "ignored" | "unsupported";
  reason: string;
}

export interface SpecGroup {
  id: string;
  label: string;
}

export interface SpecIssue {
  id: string;
  label: string;
  path: string;
  status: "ok" | "partial" | "ignored" | "unsupported";
  backtest: boolean;
  live: boolean;
  blocking: boolean;
  reason: string;
}

export interface Catalog {
  indicators: CatalogIndicator[];
  markets: CatalogMarket[];
  spec_params: SpecParam[];
  spec_features: SpecFeature[];
  spec_groups: SpecGroup[];
  spec_defaults: Record<string, unknown>;
  counts: { indicators: number; markets: number; spec_params: number };
}

export const CATALOG = catalog as unknown as Catalog;
export const SPEC_PARAMS = CATALOG.spec_params;
export const SPEC_FEATURES = CATALOG.spec_features;
export const SPEC_GROUPS = CATALOG.spec_groups;

const PARAM_BY_KEY = new Map(SPEC_PARAMS.map((p) => [p.key, p]));

export function marketById(id: string): CatalogMarket | undefined {
  return CATALOG.markets.find((m) => m.id === id);
}

export function indicatorsForMarket(marketId: string): CatalogIndicator[] {
  const m = marketById(marketId);
  if (!m) return [];
  return CATALOG.indicators.filter((ind) =>
    ind.inputs.every((i) => m.provides.includes(i)),
  );
}

export function indicatorById(id: string): CatalogIndicator | undefined {
  return CATALOG.indicators.find((i) => i.id === id);
}

export function specParam(key: string): SpecParam | undefined {
  return PARAM_BY_KEY.get(key);
}

export function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export function getPath(obj: unknown, path: string): unknown {
  let cur: unknown = obj;
  for (const part of path.split(".")) {
    if (typeof cur !== "object" || cur === null || !(part in cur)) return undefined;
    cur = (cur as Record<string, unknown>)[part];
  }
  return cur;
}

export function setPath<T>(obj: T, path: string, value: unknown): T {
  const out = clone(obj) as Record<string, unknown>;
  const parts = path.split(".");
  let cur: Record<string, unknown> = out;
  for (const part of parts.slice(0, -1)) {
    const next = cur[part];
    if (typeof next !== "object" || next === null || Array.isArray(next)) {
      const made: Record<string, unknown> = {};
      cur[part] = made;
      cur = made;
    } else {
      cur = next as Record<string, unknown>;
    }
  }
  const last = parts[parts.length - 1];
  if (value === undefined || value === null) delete cur[last];
  else cur[last] = clone(value);
  return out as T;
}

export function defaultSpec<T = Record<string, unknown>>(universe: string): T {
  const spec = clone(CATALOG.spec_defaults);
  spec.universe = universe;
  return spec as T;
}

export function visibleParam(p: SpecParam, spec: unknown): boolean {
  if (!p.visible_if) return true;
  const v = getPath(spec, p.visible_if.path);
  if (p.visible_if.exists !== undefined) {
    return (v !== undefined && v !== null) === p.visible_if.exists;
  }
  if (p.visible_if.in) return p.visible_if.in.includes(v);
  if ("equals" in p.visible_if) return v === p.visible_if.equals;
  return true;
}

export function featureActive(f: SpecFeature, spec: unknown): boolean {
  const v = getPath(spec, f.path);
  if (f.op === "exists") return v !== undefined && v !== null;
  if (f.op === "nonempty") return Array.isArray(v) ? v.length > 0 : Boolean(v);
  if (f.op === "neq") return v !== undefined && v !== null && v !== f.value;
  if (f.op === "in") return (f.values ?? []).includes(v);
  return v === f.value;
}

export function specIssues(spec: unknown, target: "backtest" | "live"): SpecIssue[] {
  const out: SpecIssue[] = [];
  for (const f of SPEC_FEATURES) {
    if (!featureActive(f, spec)) continue;
    const supported = f[target];
    if (supported && f.status === "ok") continue;
    out.push({
      id: f.id,
      label: f.label,
      path: f.path,
      status: f.status,
      backtest: f.backtest,
      live: f.live,
      blocking: !supported,
      reason: f.reason,
    });
  }
  return out;
}

export function blockingIssues(spec: unknown, target: "backtest" | "live"): SpecIssue[] {
  return specIssues(spec, target).filter((i) => i.blocking);
}

export function paramsForGroup(group: string): SpecParam[] {
  return SPEC_PARAMS.filter((p) => p.group === group);
}
