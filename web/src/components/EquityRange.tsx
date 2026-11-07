import { useId, useMemo, useState } from "react";
import { DEFAULT_BOT_COLOR } from "../lib/brand";
import { dol, pct } from "../lib/format";
import RangeBrush from "./RangeBrush";
import s from "./EquityRange.module.css";

type Pt = [number, number]; // [timestamp, equity]

/** Equity curve with a CoinMarketCap-style two-handle range brush. The main
 *  chart and the $start → $end readout describe only the selected window, so
 *  "from here to here it was actually profitable" is a drag away. */
export default function EquityRange({ pts: raw, color }: { pts: Pt[]; color?: string }) {
  const uid = useId();
  const col = color || DEFAULT_BOT_COLOR;

  // engine timestamps are ms; tolerate seconds from older rows
  const pts = useMemo(
    () => raw.map(([t, e]) => [t < 1e11 ? t * 1000 : t, e] as Pt),
    [raw],
  );
  const t0 = pts[0][0];
  const t1 = pts[pts.length - 1][0];

  const [sel, setSel] = useState<[number, number]>([0, 1]);
  const a = t0 + sel[0] * (t1 - t0);
  const b = t0 + sel[1] * (t1 - t0);

  const slice = useMemo(() => {
    let lo = pts.findIndex((d) => d[0] >= a);
    if (lo < 0) lo = pts.length - 1;
    let hi = pts.length - 1;
    while (hi > 0 && pts[hi][0] > b) hi--;
    // always keep at least two points so the window never collapses to nothing
    if (hi <= lo) {
      if (lo >= pts.length - 1) lo = pts.length - 2;
      hi = lo + 1;
    }
    return pts.slice(lo, hi + 1);
  }, [pts, a, b]);

  const e0 = slice[0][1];
  const e1 = slice[slice.length - 1][1];
  const ret = e0 ? (e1 / e0 - 1) * 100 : 0;
  const up = e1 >= e0;

  const path = (data: Pt[], W: number, H: number, padY: number) => {
    const xs = data.map((d) => d[0]);
    const ys = data.map((d) => d[1]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs);
    const lo = Math.min(...ys), hi = Math.max(...ys);
    const X = (t: number) => ((t - x0) / (x1 - x0 || 1)) * W;
    const Y = (v: number) => H - padY - ((v - lo) / (hi - lo || 1)) * (H - padY * 2);
    const line = data.map((d, i) => (i ? "L" : "M") + X(d[0]).toFixed(1) + " " + Y(d[1]).toFixed(1)).join(" ");
    const area = `M${X(data[0][0]).toFixed(1)} ${H} ` +
      data.map((d) => "L" + X(d[0]).toFixed(1) + " " + Y(d[1]).toFixed(1)).join(" ") +
      ` L${X(data[data.length - 1][0]).toFixed(1)} ${H} Z`;
    return { line, area };
  };
  const main = path(slice, 1000, 240, 6);

  const span = b - a;
  const DAY = 86_400_000;
  const tick = (t: number) => {
    const d = new Date(t);
    if (span > 240 * DAY) return d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
    if (span > 3 * DAY) return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    return (
      d.toLocaleDateString("en-US", { month: "short", day: "numeric" }) +
      " " + d.toLocaleTimeString("en-US", { hour: "numeric" })
    );
  };
  const full = (t: number) =>
    new Date(t).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  const ticks = [0, 1 / 3, 2 / 3, 1].map((f) => tick(a + f * span));

  return (
    <div>
      <div className={s.readout}>
        <span className={`${s.dates} num`}>{full(a)} → {full(b)}</span>
        <span className={`${s.money} num`}>
          {dol(e0)} → {dol(e1)}
          <b className={up ? "up" : "down"}>{pct(ret, true)}</b>
        </span>
      </div>

      <svg
        viewBox="0 0 1000 240"
        preserveAspectRatio="none"
        style={{ width: "100%", height: 240, display: "block", marginTop: 10 }}
      >
        <defs>
          <linearGradient id={uid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={col} stopOpacity="0.16" />
            <stop offset="1" stopColor={col} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={main.area} fill={`url(#${uid})`} />
        <path d={main.line} fill="none" stroke={col} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
      </svg>
      <div className={`${s.ticks} num`}>
        {ticks.map((t, i) => <span key={i}>{t}</span>)}
      </div>

      <div style={{ marginTop: 12 }}>
        <RangeBrush pts={pts} value={sel} onChange={setSel} color={col} />
      </div>
    </div>
  );
}
