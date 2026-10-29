import { useEffect, useRef, useState } from "react";

/** A number that rolls to its value instead of snapping — odometer feel. On
 *  mount it counts up from 0; on each update it glides from the previous value,
 *  so the live fleet figures animate instead of ticking/flashing. */
export default function Rolling({
  value,
  format,
  duration = 650,
}: {
  value: number;
  format: (n: number) => string;
  duration?: number;
}) {
  const [disp, setDisp] = useState(0);
  const fromRef = useRef(0);

  useEffect(() => {
    const from = fromRef.current;
    const to = Number.isFinite(value) ? value : 0;
    if (from === to) {
      setDisp(to);
      return;
    }
    let raf = 0;
    const start = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3); // easeOutCubic
      setDisp(from + (to - from) * eased);
      if (t < 1) raf = requestAnimationFrame(step);
      else fromRef.current = to;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);

  return <>{format(disp)}</>;
}
