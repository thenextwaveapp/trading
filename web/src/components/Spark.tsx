/** Sparkline from data points. */
export default function Spark({
  data,
  w = 240,
  h = 50,
  up = true,
  color,
}: {
  data: number[];
  w?: number;
  h?: number;
  up?: boolean;
  color?: string;
}) {
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
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <path d={d} fill="none" stroke={color || (up ? "#3DDC97" : "#FF5C6C")} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
