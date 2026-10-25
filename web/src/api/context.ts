import { createContext, useContext } from "react";
import type { Payload } from "./types";

/** Latest /api payload, provided by <App> and consumed everywhere. */
export const FleetCtx = createContext<Payload | null>(null);

export function useData(): Payload {
  const d = useContext(FleetCtx);
  if (!d) throw new Error("useData must be used within <FleetCtx.Provider>");
  return d;
}

/** An empty-but-valid payload. Lets the app render its shell and public pages
 *  (and every data page's empty state) when the live fleet feed is down,
 *  instead of hard-blocking the whole site on a reachable backend. */
export const EMPTY_PAYLOAD: Payload = {
  now: Date.now(),
  start: Date.now(),
  gate: { bear: null },
  hero: {
    base_pnl: 0, base_ret: 0, base_closed: 0, base_avg: null, bench: 0,
    fleet_pnl: 0, unreal: 0, week_pnl: 0, closed: 0,
  },
  variants: [],
  strats: {},
  positions: [],
  trades: [],
  log: [],
  running: null,
  loaded: false,
  paused: false,
  health: { status: "red", msg: "" },
  ntfy: "",
  state_age_s: null,
  symbols: {},
};
