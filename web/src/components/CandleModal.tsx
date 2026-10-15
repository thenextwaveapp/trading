import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useLocation } from "react-router-dom";
import {
  createChart,
  LineStyle,
  type ISeriesApi,
  type SeriesMarker,
  type UTCTimestamp,
} from "lightweight-charts";
import { fetchCandles } from "../api/client";
import type { Candle } from "../api/types";
import { lt } from "../lib/format";
import { LW_OPTS } from "./FleetChart";
import s from "./CandleModal.module.css";

export interface CandleReq {
  sym: string;
  title: string;
  t_sig: number;
  entry: number;
  stop?: number | null;
  tp?: number | null;
  exit_t?: number | null;
  kind?: string | null;
  side?: string | null;
}

const CandleCtx = createContext<(r: CandleReq) => void>(() => {});
export const useCandle = () => useContext(CandleCtx);

const IVMS: Record<string, number> = {
  "15m": 900_000,
  "1h": 3_600_000,
  "4h": 14_400_000,
  "1d": 86_400_000,
};

export function CandleProvider({ children }: { children: ReactNode }) {
  const [req, setReq] = useState<CandleReq | null>(null);
  const loc = useLocation();
  const open = useCallback((r: CandleReq) => {
    if (r.sym) setReq(r);
  }, []);
  // close the chart when navigating between fleet / bot pages
  useEffect(() => setReq(null), [loc.pathname]);
  return (
    <CandleCtx.Provider value={open}>
      {children}
      {req && <Modal req={req} onClose={() => setReq(null)} />}
    </CandleCtx.Provider>
  );
}

function Modal({ req, onClose }: { req: CandleReq; onClose: () => void }) {
  const elRef = useRef<HTMLDivElement>(null);
  const [iv, setIv] = useState("15m");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    const el = elRef.current;
    if (!el) return;
    const ivms = IVMS[iv];
    const snap = (t: number) => t - (t % ivms);

    const chart = createChart(el, LW_OPTS);
    const ser: ISeriesApi<"Candlestick"> = chart.addCandlestickSeries({
      upColor: "#3DDC97",
      downColor: "#FF5C6C",
      wickUpColor: "#3DDC97",
      wickDownColor: "#FF5C6C",
      borderVisible: false,
    });
    const priceLine = (p: number | null | undefined, color: string, title: string) =>
      p && ser.createPriceLine({ price: p, color, lineWidth: 1, lineStyle: LineStyle.Dashed, title });
    priceLine(req.entry, "#58a6ff", "entry");
    priceLine(req.stop, "#FF5C6C", "stop");
    priceLine(req.tp, "#3DDC97", "tp");

    let data: Candle[] = [];
    let loading = false;
    let more = true;
    let dead = false;

    const applyMarkers = () => {
      const mk: SeriesMarker<UTCTimestamp>[] = [
        {
          time: lt(snap(req.t_sig)) as UTCTimestamp,
          position: req.side === "short" ? "aboveBar" : "belowBar",
          color: "#58a6ff",
          shape: req.side === "short" ? "arrowDown" : "arrowUp",
          text: "in",
        },
      ];
      if (req.exit_t)
        mk.push({
          time: lt(snap(req.exit_t)) as UTCTimestamp,
          position: "inBar",
          color: "#d29922",
          shape: "circle",
          text: req.kind || "out",
        });
      const first = data.length ? lt(data[0].t) : 0;
      ser.setMarkers(mk.filter((m) => (m.time as number) >= first).sort((a, b) => (a.time as number) - (b.time as number)));
    };

    const render = () => {
      ser.setData(
        data.map((c) => ({ time: lt(c.t) as UTCTimestamp, open: c.o, high: c.h, low: c.l, close: c.c })),
      );
      applyMarkers();
    };

    const loadInitial = async () => {
      loading = true;
      more = true;
      let k: Candle[];
      if (req.exit_t) {
        const start = snap(req.t_sig) - 60 * ivms;
        const limit = Math.min(Math.ceil((req.exit_t - start) / ivms) + 40, 1500);
        k = await fetchCandles({ symbol: req.sym, interval: iv, start, limit });
      } else {
        k = await fetchCandles({ symbol: req.sym, interval: iv, limit: 420 });
      }
      if (dead) return;
      data = k;
      render();
      chart.timeScale().fitContent();
      loading = false;
    };

    const loadOlder = async () => {
      if (loading || !more || !data.length) return;
      loading = true;
      const k = await fetchCandles({ symbol: req.sym, interval: iv, end: data[0].t - 1, limit: 1000 });
      if (dead) return;
      if (!k.length) more = false;
      else {
        const last = k[k.length - 1].t;
        data = k.concat(data.filter((c) => c.t > last));
      }
      render();
      loading = false;
    };

    chart.timeScale().subscribeVisibleLogicalRangeChange((r) => {
      if (r && r.from < 30) void loadOlder();
    });
    void loadInitial();

    return () => {
      dead = true;
      chart.remove();
    };
  }, [iv, req]);

  return (
    <div
      className={s.overlay}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className={s.box}>
        <div className={s.head}>
          <b className={s.title}>{req.title}</b>
          <div className={s.iv}>
            {Object.keys(IVMS).map((k) => (
              <button key={k} className={`${s.ivb} ${iv === k ? s.sel : ""}`} onClick={() => setIv(k)}>
                {k}
              </button>
            ))}
          </div>
          <button className={s.close} onClick={onClose} aria-label="close">
            ✕
          </button>
        </div>
        <div ref={elRef} className={s.chart} />
        <div className={s.hint}>scroll left to load older history · drag to pan · wheel to zoom</div>
      </div>
    </div>
  );
}
