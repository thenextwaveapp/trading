import { createContext, useContext } from "react";
import type { Payload } from "./types";

/** Latest /api payload, provided by <App> and consumed everywhere. */
export const FleetCtx = createContext<Payload | null>(null);

export function useData(): Payload {
  const d = useContext(FleetCtx);
  if (!d) throw new Error("useData must be used within <FleetCtx.Provider>");
  return d;
}
