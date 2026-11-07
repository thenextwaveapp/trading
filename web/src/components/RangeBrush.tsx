import { useRef } from "react";
import { DEFAULT_BOT_COLOR } from "../lib/brand";
import s from "./RangeBrush.module.css";

type Pt = [number, number];

const MIN_SPAN = 0.01;

/** Two-handle CoinMarketCap-style brush over a mini line of the full series.
 *  Controlled: `value` is [start, end] as fractions (0..1) of the pts domain.
 *  Drag a handle to resize, the body to pan, double-click to reset. */
export default function RangeBrush({ pts, value, onChange, color }: {
  pts: Pt[];
  value: [number, number];
  onChange: (v: [number, number]) => void;
  color?: string;
}) {
  const col = color || DEFAULT_BOT_COLOR;
  const ref = useRef<HTMLDivElement>(null);
  const drag = useRef<{ mode: "l" | "r" | "pan"; offset: number } | null>(null);

  const fracOf = (clientX: number) => {
    const rect = ref.current!.getBoundingClientRect();
    return Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
  };
  const move = (f: number, mode: "l" | "r" | "pan", offset = 0) => {
    const [s0, s1] = value;
    if (mode === "l") onChange([Math.min(f, s1 - MIN_SPAN), s1]);
    else if (mode === "r") onChange([s0, Math.max(f, s0 + MIN_SPAN)]);
    else {
      const w = s1 - s0;
      const ns0 = Math.min(1 - w, Math.max(0, f - offset));
      onChange([ns0, ns0 + w]);
    }
  };
  const onDown = (e: React.PointerEvent) => {
    const f = fracOf(e.clientX);
    const h = (e.target as HTMLElement).dataset?.h;
    let mode: "l" | "r" | "pan";
    if (h === "l" || h === "r") mode = h;
    else if (f >= value[0] && f <= value[1]) mode = "pan";
    else mode = Math.abs(f - value[0]) < Math.abs(f - value[1]) ? "l" : "r";
    drag.current = { mode, offset: f - value[0] };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    if (mode !== "pan") move(f, mode);
  };
  const onMove = (e: React.PointerEvent) => {
    if (!drag.current) return;
    move(fracOf(e.clientX), drag.current.mode, drag.current.offset);
  };
  const onUp = () => (drag.current = null);

  // mini line over the full domain
  const xs = pts.map((d) => d[0]);
  const ys = pts.map((d) => d[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const lo = Math.min(...ys), hi = Math.max(...ys);
  const X = (t: number) => ((t - x0) / (x1 - x0 || 1)) * 1000;
  const Y = (v: number) => 40 - ((v - lo) / (hi - lo || 1)) * 36;
  const line = pts.map((d, i) => (i ? "L" : "M") + X(d[0]).toFixed(1) + " " + Y(d[1]).toFixed(1)).join(" ");

  return (
    <div
      ref={ref}
      className={s.brush}
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerCancel={onUp}
      onDoubleClick={() => onChange([0, 1])}
      title="Drag the handles to zoom a window · drag the middle to pan · double-click to reset"
    >
      <svg viewBox="0 0 1000 44" preserveAspectRatio="none">
        <path d={line} fill="none" stroke={col} strokeOpacity="0.8" strokeWidth={1} vectorEffect="non-scaling-stroke" />
      </svg>
      <div className={s.shade} style={{ left: 0, width: `${value[0] * 100}%` }} />
      <div className={s.shade} style={{ left: `${value[1] * 100}%`, right: 0 }} />
      <div className={s.window} style={{ left: `${value[0] * 100}%`, width: `${(value[1] - value[0]) * 100}%` }}>
        <span className={`${s.grip} ${s.gripL}`} data-h="l" />
        <span className={`${s.grip} ${s.gripR}`} data-h="r" />
      </div>
    </div>
  );
}
