import { useEffect, useRef, useState } from "react";
import { createChart, type ISeriesApi, type UTCTimestamp } from "lightweight-charts";
import { fetchCandles } from "../api/client";
import type { Candle } from "../api/types";
import { lt } from "../lib/format";
import { LW_OPTS } from "./FleetChart";

const IVS = ["15m", "1h", "4h", "1d"] as const;

/** Embedded price chart for a symbol — same lib + data path as CandleModal,
 *  without the trade overlay. The web only renders; candles come from the
 *  shared fetchCandles. */
export default function CandleChart({ sym, height = 440 }: { sym: string; height?: number }) {
  const elRef = useRef<HTMLDivElement>(null);
  const [iv, setIv] = useState<(typeof IVS)[number]>("1h");

  useEffect(() => {
    const el = elRef.current;
    if (!el) return;
    const chart = createChart(el, { ...LW_OPTS, height, width: el.clientWidth });
    const ser: ISeriesApi<"Candlestick"> = chart.addCandlestickSeries({
      upColor: "#3DDC97", downColor: "#FF5C6C",
      wickUpColor: "#3DDC97", wickDownColor: "#FF5C6C", borderVisible: false,
    });
    let dead = false;
    (async () => {
      const k: Candle[] = await fetchCandles({ symbol: sym, interval: iv, limit: 500 });
      if (dead) return;
      ser.setData(k.map((c) => ({
        time: lt(c.t) as UTCTimestamp, open: c.o, high: c.h, low: c.l, close: c.c,
      })));
      chart.timeScale().fitContent();
    })();
    const onResize = () => chart.applyOptions({ width: el.clientWidth });
    window.addEventListener("resize", onResize);
    return () => {
      dead = true;
      window.removeEventListener("resize", onResize);
      chart.remove();
    };
  }, [sym, iv, height]);

  return (
    <div>
      <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
        {IVS.map((x) => (
          <button
            key={x}
            onClick={() => setIv(x)}
            className="chip"
            style={{
              cursor: "pointer",
              color: x === iv ? "var(--fg)" : "var(--muted)",
              background: x === iv ? "#171c24" : "transparent",
            }}
          >
            {x}
          </button>
        ))}
      </div>
      <div ref={elRef} style={{ width: "100%", height }} />
    </div>
  );
}
