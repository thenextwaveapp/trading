import { useId } from "react";

/** Sparkline from data points. `area` fills a soft gradient under the line. */
export default function Spark({
  data,
  w = 240,
  h = 50,
  up = true,
  color,
  area = false,
}: {
  data: number[];
  w?: number;
  h?: number;
  up?: boolean;
  color?: string;
  area?: boolean;
}) {
  const gid = useId().replace(/:/g, "");
  // Downsample to ~48 points to keep the path light.
  let arr = data;
  if (arr.length > 48) {
    const stride = Math.ceil(arr.length / 48);
    arr = arr.filter((_, i) => i % stride === 0 || i === data.length - 1);
  }
  if (arr.length < 2) arr = [arr[0] ?? 0, arr[0] ?? 0];
  const T = arr.length;
  const lo = Math.min(...arr);
  const hi = Math.max(...arr);
  const X = (i: number) => (i / (T - 1)) * w;
  const Y = (x: number) => h - 4 - ((x - lo) / (hi - lo || 1)) * (h - 8);
  const d = arr.map((x, i) => (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(x).toFixed(1)).join(" ");
  const stroke = color || (up ? "#3DDC97" : "#FF5C6C");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      {area && (
        <>
          <defs>
            <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity="0.22" />
              <stop offset="100%" stopColor={stroke} stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={`${d} L ${w.toFixed(1)} ${h} L 0 ${h} Z`} fill={`url(#${gid})`} stroke="none" />
        </>
      )}
      <path d={d} fill="none" stroke={stroke} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
