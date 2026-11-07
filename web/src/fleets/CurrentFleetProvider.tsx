import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useAuth } from "../auth";
import { fetchMyFleets, useQuery } from "../db/queries";
import type { DbFleet } from "../db/types";

/** The fleet the user is currently looking at / deploying into. The DB has had
 *  multi-fleet columns for a while (pf_fleets, pf_bots.fleet_id); this is the
 *  shared selection that finally surfaces it — the fleet page filters by it and
 *  Settings manages the list. Mirrors the AssistantProvider pattern: one context,
 *  the choice persisted in localStorage so it survives reloads.
 *
 *  The list is held as state, seeded once from the query, then mutated
 *  optimistically on create/edit/delete — so a freshly made fleet is valid the
 *  instant it's selected, with no refetch race against the reconcile below. */
interface CurrentFleetApi {
  fleets: DbFleet[];
  current: DbFleet | null;
  currentId: string | null;
  setCurrentId: (id: string) => void;
  /** Add or replace a fleet locally (after createFleet / updateFleet). */
  upsertFleet: (f: DbFleet) => void;
  /** Drop a fleet locally (after deleteFleet). */
  removeFleet: (id: string) => void;
  loading: boolean;
}

const Ctx = createContext<CurrentFleetApi | null>(null);
export const useCurrentFleet = (): CurrentFleetApi => {
  const v = useContext(Ctx);
  if (!v) throw new Error("useCurrentFleet outside provider");
  return v;
};

const KEY = "pf_current_fleet";

export function CurrentFleetProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const { data } = useQuery<DbFleet[]>(
    () => (user ? fetchMyFleets(user.id) : Promise.resolve({ data: [], error: null })),
    [user?.id],
  );

  const [fleets, setFleets] = useState<DbFleet[]>([]);
  // Seed (and re-seed on sign-in change) from the server. We never refetch after
  // mount, so optimistic edits below are safe from being clobbered.
  useEffect(() => {
    if (data) setFleets(data);
  }, [data]);

  const [currentId, setCurrentIdState] = useState<string | null>(() => localStorage.getItem(KEY));

  // Keep the selection pointing at a real fleet: fall back to the first one if
  // nothing is chosen or the saved/removed id is no longer present.
  useEffect(() => {
    if (!fleets.length) return;
    if (!currentId || !fleets.some((f) => f.id === currentId)) {
      setCurrentIdState(fleets[0].id);
    }
  }, [fleets, currentId]);

  const setCurrentId = useCallback((id: string) => {
    localStorage.setItem(KEY, id);
    setCurrentIdState(id);
  }, []);

  const upsertFleet = useCallback((f: DbFleet) => {
    setFleets((cur) => {
      const i = cur.findIndex((x) => x.id === f.id);
      if (i < 0) return [...cur, f];
      const copy = cur.slice();
      copy[i] = f;
      return copy;
    });
  }, []);

  const removeFleet = useCallback((id: string) => {
    setFleets((cur) => cur.filter((x) => x.id !== id));
  }, []);

  const current = useMemo(
    () => fleets.find((f) => f.id === currentId) ?? null,
    [fleets, currentId],
  );

  const api = useMemo<CurrentFleetApi>(
    () => ({ fleets, current, currentId, setCurrentId, upsertFleet, removeFleet, loading: data === null }),
    [fleets, current, currentId, setCurrentId, upsertFleet, removeFleet, data],
  );

  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}
