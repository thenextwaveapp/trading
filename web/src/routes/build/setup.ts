import type { Direction } from "../../db/types";

/** The families whose Setup the engine can actually map today
 *  (core/mapping.py). Everything else is visible but not trainable yet. */
export const MAPPABLE_FAMILIES = new Set([
  "pump_short",
  "two_sided",
  "capit_long",
  "momo_long",
]);

export interface SetupField {
  key: string;
  label: string;
  hint: string;
  min: number;
  max: number;
  step: number;
  /** percent values are stored as fractions (0.12) but edited as 12. */
  scale: "percent" | "multiple" | "bars";
}

export interface FamilySetup {
  direction: Direction;
  fields: SetupField[];
  defaults: Record<string, number>;
  stop: [string, number];
  extras: Record<string, unknown>;
  note?: string;
}

const PUMP_FIELDS: SetupField[] = [
  { key: "runup", label: "Run-up", hint: "4h move that defines a pump", min: 1, max: 100, step: 0.5, scale: "percent" },
  { key: "vol", label: "Volume", hint: "vs the prior 8-bar average", min: 0.5, max: 20, step: 0.1, scale: "multiple" },
  { key: "hold", label: "Hold", hint: "maximum bars in the trade", min: 1, max: 384, step: 1, scale: "bars" },
];

export const FAMILY_SETUP: Record<string, FamilySetup> = {
  pump_short: {
    direction: "short",
    fields: PUMP_FIELDS,
    defaults: { runup: 0.12, vol: 2.0, hold: 16 },
    stop: ["hh", 0.0],
    extras: {},
  },
  two_sided: {
    direction: "both",
    fields: PUMP_FIELDS,
    defaults: { runup: 0.12, vol: 2.0, hold: 16 },
    stop: ["hh", 0.0],
    extras: { twosided: true },
    note: "Only the short book is mapped by the engine, so this family can train but cannot deploy yet — the long book is a future release.",
  },
  capit_long: {
    direction: "long",
    fields: [
      { key: "depth", label: "Crash depth", hint: "24h drop that triggers a buy", min: 1, max: 90, step: 0.5, scale: "percent" },
      { key: "hold", label: "Hold", hint: "maximum bars in the trade", min: 1, max: 672, step: 1, scale: "bars" },
    ],
    defaults: { depth: 0.2, hold: 96 },
    stop: ["none", 0.0],
    extras: {},
  },
  momo_long: {
    direction: "long",
    fields: [
      { key: "runup", label: "Breakout", hint: "4h move required", min: 1, max: 100, step: 0.5, scale: "percent" },
      { key: "vol", label: "Volume", hint: "vs the prior 8-bar average", min: 0.5, max: 20, step: 0.1, scale: "multiple" },
      { key: "hold", label: "Hold", hint: "maximum bars in the trade", min: 1, max: 384, step: 1, scale: "bars" },
    ],
    defaults: { runup: 0.12, vol: 2.5, hold: 48 },
    stop: ["sig", 0.0],
    extras: {},
  },
};

export function familySetup(slug: string | null | undefined): FamilySetup | null {
  return slug ? FAMILY_SETUP[slug] ?? null : null;
}

/** Engine param units -> editor values (0.12 -> 12, 2.0 -> 2). */
function display(field: SetupField, raw: unknown): number {
  const n = typeof raw === "number" && isFinite(raw) ? raw : 0;
  return field.scale === "percent" ? Math.round(n * 10000) / 100 : n;
}

/** Editor values -> engine param units. */
function param(field: SetupField, shown: unknown): number {
  const n = typeof shown === "number" && isFinite(shown) ? shown : 0;
  return field.scale === "percent" ? n / 100 : n;
}

const round = (n: number, step: number) => {
  const d = String(step).split(".")[1]?.length ?? 0;
  return Number(n.toFixed(d));
};

export function setupFromParams(
  slug: string,
  params: Record<string, unknown>,
): { values: Record<string, number>; extras: Record<string, unknown> } {
  const setup = familySetup(slug);
  if (!setup) return { values: {}, extras: { ...params } };
  const values: Record<string, number> = {};
  for (const f of setup.fields) {
    const raw = params[f.key] ?? setup.defaults[f.key];
    values[f.key] = round(display(f, raw), f.scale === "percent" ? 0.01 : f.step);
  }
  const known = new Set([...setup.fields.map((f) => f.key), "stop", ...Object.keys(setup.extras)]);
  const extras: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(params)) if (!known.has(k)) extras[k] = v;
  return { values, extras };
}

export function defaultsFor(slug: string | null | undefined): Record<string, number> {
  const setup = familySetup(slug);
  if (!setup) return {};
  const values: Record<string, number> = {};
  for (const f of setup.fields) values[f.key] = display(f, setup.defaults[f.key]);
  return values;
}

export function paramsFromSetup(
  slug: string,
  values: Record<string, number>,
  extras: Record<string, unknown>,
): Record<string, unknown> {
  const setup = familySetup(slug);
  if (!setup) return { ...values, ...extras };
  const params: Record<string, unknown> = { ...setup.extras, ...extras };
  for (const f of setup.fields) params[f.key] = param(f, values[f.key]);
  params.stop = setup.stop;
  return params;
}

export interface SetupIssue {
  key: string;
  message: string;
}

export function validateSetup(
  slug: string,
  values: Record<string, number>,
): SetupIssue[] {
  const setup = familySetup(slug);
  if (!setup) return [{ key: "family", message: "Pick a trainable family." }];
  const out: SetupIssue[] = [];
  for (const f of setup.fields) {
    const v = values[f.key];
    if (typeof v !== "number" || !isFinite(v)) {
      out.push({ key: f.key, message: `${f.label} is required.` });
    } else if (v < f.min || v > f.max) {
      out.push({ key: f.key, message: `${f.label} must be ${f.min}–${f.max}.` });
    }
  }
  return out;
}

export function nameIssue(name: string): string | null {
  const n = name.trim();
  if (!n) return "Give the bot a name.";
  if (n.length > 48) return "Keep the name under 48 characters.";
  return null;
}

const pctText = (x: number) =>
  `${Number((x * 100).toFixed(2))}%`;

export function barsText(bars: number): string {
  const mins = Math.round(bars * 15);
  if (mins < 60) return `${mins} min`;
  if (mins < 24 * 60) {
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return m ? `${h}h ${m}m` : `${h}h`;
  }
  return `${Math.round(mins / (24 * 60))} days`;
}

/** Plain-language preview of exactly what the engine will run. */
export function previewRules(
  slug: string,
  params: Record<string, unknown>,
): { entry: string[]; exit: string; note?: string } {
  const setup = familySetup(slug);
  if (!setup) return { entry: [], exit: "" };
  const n = (k: string, fallback: number) =>
    typeof params[k] === "number" ? (params[k] as number) : fallback;
  const hold = Math.max(1, Math.round(n("hold", setup.defaults.hold)));
  const runup = n("runup", setup.defaults.runup ?? 0.12);
  const vol = n("vol", setup.defaults.vol ?? 2);
  const depth = n("depth", setup.defaults.depth ?? 0.2);
  const wick = params.wick;

  if (slug === "pump_short" || slug === "two_sided") {
    const entry = [
      `Price is up at least ${pctText(runup)} over the last 4 hours.`,
      "The candle closes red — the first down bar after the run.",
      `Volume is at least ${vol}× the prior 8-bar average.`,
    ];
    if (typeof wick === "number") {
      entry.push(`The upper wick is at least ${pctText(wick)} of the 4h range.`);
    }
    return {
      entry,
      exit: `Cover after ${hold} bars (${barsText(hold)}) or if price trades above the 4h signal high.`,
      note: setup.note,
    };
  }

  if (slug === "capit_long") {
    return {
      entry: [
        `Price is down at least ${pctText(depth)} over the last 24 hours.`,
        "The drop is fresh — it was not already this deep on the prior bar.",
      ],
      exit: `Sell after ${hold} bars (${barsText(hold)}). No stop; time is the exit.`,
    };
  }

  if (slug === "momo_long") {
    return {
      entry: [
        `Price is up at least ${pctText(runup)} over the last 4 hours.`,
        `Volume is at least ${vol}× the prior 8-bar average.`,
        "The candle closes strong: upper wick ≤ 15% and close in the top 20% of the 4h range.",
      ],
      exit: `Sell after ${hold} bars (${barsText(hold)}) or on the signal-window stop (the 4h low or midpoint).`,
    };
  }

  return { entry: [], exit: "" };
}
