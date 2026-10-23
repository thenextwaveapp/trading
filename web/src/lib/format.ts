// Shared formatters.

export const START = 10_000;

export function usd(n: number | null | undefined, signed = false): string {
  if (n == null || isNaN(n)) return "–";
  const a = Math.abs(n).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return (n < 0 ? "−" : signed ? "+" : "") + "$" + a;
}

export function dol(n: number): string {
  return (
    "$" +
    Number(n).toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
  );
}

export function pct(n: number | null | undefined, signed = false): string {
  if (n == null || isNaN(n)) return "–";
  const abs = Math.abs(n);
  return (n < 0 ? "−" : signed ? "+" : "") + abs.toFixed(abs < 10 ? 2 : 1) + "%";
}

export function px(x: number | null | undefined | string): string {
  if (x == null || x === "" || isNaN(Number(x))) return "–";
  const v = Number(x);
  const a = Math.abs(v);
  const d = a >= 100 ? 2 : a >= 1 ? 3 : a >= 0.01 ? 4 : 6;
  return v.toFixed(d).replace(/\.?0+$/, (m) => (m.includes(".") ? "" : m));
}

const p2 = (n: number) => String(n).padStart(2, "0");

export function clock(ms: number): string {
  const d = new Date(ms);
  return p2(d.getHours()) + ":" + p2(d.getMinutes());
}

export function dstr(ms: number): string {
  return new Date(ms).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

export function held(ms: number): string {
  const m = Math.round(ms / 60_000);
  if (m < 60) return m + "m";
  const h = Math.floor(m / 60);
  const mm = m % 60;
  if (h < 48) return h + "h" + (mm ? " " + p2(mm) + "m" : "");
  return Math.round(h / 24) + "d";
}

export function dur(ms: number): string {
  const m = Math.max(0, Math.round(ms / 60_000));
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return (h ? h + "h " : "") + p2(mm) + "m";
}

export function ago(s: number | null): string {
  if (s == null) return "—";
  if (s < 90) return s + "s ago";
  if (s < 5400) return Math.round(s / 60) + "m ago";
  if (s < 172800) return Math.round(s / 3600) + "h ago";
  return Math.round(s / 86400) + "d ago";
}

export const REASON: Record<string, string> = {
  sl: "Stop loss",
  time: "Time limit",
  tp: "Take profit",
  manual: "Closed manually",
  trail: "Trailing stop",
};

export const DIRLBL: Record<string, string> = {
  short: "Short",
  long: "Long",
  both: "Two-sided",
};

/** Deterministic 3x5 pixel identicon path, seeded by name. */
export function identicon(seed: string, size: number): string {
  let h = 7;
  for (const c of seed) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  let d = "";
  const u = size / 5;
  for (let y = 0; y < 5; y++)
    for (let x = 0; x < 3; x++) {
      h = (h * 1103515245 + 12345) >>> 0;
      if ((h >>> 16) & 1) {
        d += `M${x * u} ${y * u}h${u}v${u}h-${u}z`;
        if (x < 2) d += `M${(4 - x) * u} ${y * u}h${u}v${u}h-${u}z`;
      }
    }
  return d || "M8 8h4v4h-4z";
}

/** LW charts render in UTC; shift ms-epoch to local so axes read local time. */
export const lt = (t: number): number =>
  Math.floor(t / 1000) - new Date(t).getTimezoneOffset() * 60;

export const TZ = Intl.DateTimeFormat().resolvedOptions().timeZone;

/** Equity value at/just-before time t in a [t,eq] curve (binary search). */
export function curveAt(curve: [number, number][], t: number): number {
  if (!curve.length) return START;
  if (t <= curve[0][0]) return curve[0][1];
  let lo = 0,
    hi = curve.length - 1,
    ans = curve[0][1];
  while (lo <= hi) {
    const m = (lo + hi) >> 1;
    if (curve[m][0] <= t) {
      ans = curve[m][1];
      lo = m + 1;
    } else hi = m - 1;
  }
  return ans;
}

/** % return of an equity curve over the last `days` (null = whole history). */
export function windowReturn(curve: [number, number][], days: number | null, now: number): number {
  if (!curve.length) return 0;
  const end = curve[curve.length - 1][1];
  const start = days == null ? curve[0][1] : curveAt(curve, now - days * 86_400_000);
  return start ? (end / start - 1) * 100 : 0;
}

/** Chart line colour by variant index (12-colour cycle). */
export function vcolor(i: number): string {
  const palette = [
    "#58a6ff", "#3fb950", "#f85149", "#d29922", "#bc8cff", "#39c5cf",
    "#ff7b72", "#7ee787", "#ffa657", "#79c0ff", "#d2a8ff", "#56d4dd",
  ];
  return palette[((i % palette.length) + palette.length) % palette.length];
}
