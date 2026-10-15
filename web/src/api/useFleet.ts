import { useEffect, useRef, useState } from "react";
import { fetchPayload } from "./client";
import type { Payload } from "./types";

export interface FleetState {
  data: Payload | null;
  error: string | null;
  loading: boolean;
}

/** Polls /api every `intervalMs` (default 10s), like the original dashboard. */
export function useFleet(intervalMs = 10_000): FleetState {
  const [data, setData] = useState<Payload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dataRef = useRef<Payload | null>(null);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;

    const tick = async () => {
      try {
        const p = await fetchPayload();
        if (!alive) return;
        dataRef.current = p;
        setData(p);
        setError(null);
      } catch (e) {
        if (!alive) return;
        // keep last-good data; only surface error if we have nothing
        if (!dataRef.current) setError((e as Error).message);
      } finally {
        if (alive) timer = setTimeout(tick, intervalMs);
      }
    };

    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [intervalMs]);

  return { data, error, loading: data === null && error === null };
}
