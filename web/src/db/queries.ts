import { useEffect, useState } from "react";
import { supabase } from "./supabase";
import type {
  DbBacktest,
  DbBot,
  DbBotVersion,
  DbCheck,
  DbCondition,
  DbFamily,
  DbFleet,
  DbPlan,
  DbProfile,
  DbStrategyCondition,
  DbUniverseFilter,
  DbUniverseWithCoins,
  Visibility,
} from "./types";

/** Tiny async-query hook for one-shot Supabase reads. */
export function useQuery<T>(
  run: () => PromiseLike<{ data: T | null; error: { message: string } | null }>,
  deps: unknown[] = [],
): { data: T | null; error: string | null; loading: boolean } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    run().then(({ data, error }) => {
      if (!alive) return;
      if (error) setError(error.message);
      else setData(data);
    });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error, loading: data === null && error === null };
}

// ---- strategy / fleet / reference ----

export const fetchBots = () =>
  supabase
    .from("pf_bots")
    .select("*, builder:pf_profiles(handle, avatar_color)")
    .neq("visibility", "private")
    .order("name");

export const fetchBot = (name: string) =>
  supabase
    .from("pf_bots")
    .select("*, builder:pf_profiles(handle, avatar_color)")
    .eq("name", name)
    .single();

/** The signed-in Builder's own bots (any stage/visibility) — their Roster. */
export const fetchMyBots = (owner: string) =>
  supabase
    .from("pf_bots")
    .select("*, builder:pf_profiles(handle, avatar_color)")
    .eq("owner", owner)
    .order("created_at", { ascending: false });

export const fetchUniverse = (slug: string) =>
  supabase
    .from("pf_universes")
    .select("*, pf_universe_coins(coin_symbol)")
    .eq("slug", slug)
    .single();

export const fetchUniverseFilters = (universeId: string) =>
  supabase.from("pf_universe_filters").select("*").eq("universe_id", universeId).order("position");

export const fetchFamilies = () => supabase.from("pf_strategy_families").select("*");

/** The signed-in Builder's fleets (the signup trigger seeds a starter one). */
export const fetchMyFleets = (owner: string) =>
  supabase.from("pf_fleets").select("*").eq("owner", owner).order("created_at");

export const fetchProfile = (handle: string) =>
  supabase.from("pf_profiles").select("*").eq("handle", handle).single();

// ---- build lifecycle ----

export const fetchBacktests = (botId: string) =>
  supabase.from("pf_backtests").select("*").eq("bot_id", botId).order("created_at", { ascending: false });

export const fetchLatestBacktest = (botId: string) =>
  supabase
    .from("pf_backtests")
    .select("*")
    .eq("bot_id", botId)
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();

export const fetchChecks = (backtestId: string) =>
  supabase.from("pf_checks").select("*").eq("backtest_id", backtestId).order("position");

export const fetchConditions = (backtestId: string) =>
  supabase.from("pf_conditions").select("*").eq("backtest_id", backtestId);

export const fetchStrategyConditions = (botId: string) =>
  supabase.from("pf_strategy_conditions").select("*").eq("bot_id", botId).order("position");

export const fetchBotVersions = (botId: string) =>
  supabase.from("pf_bot_versions").select("*").eq("bot_id", botId).order("version", { ascending: false });

// ---- account ----

export const fetchPlans = () => supabase.from("pf_plans").select("*").order("position");

// ---- typed convenience hooks ----

export const useBots = () => useQuery<DbBot[]>(() => fetchBots());
export const useMyBots = (owner: string | null) =>
  useQuery<DbBot[]>(
    () => (owner ? fetchMyBots(owner) : Promise.resolve({ data: [], error: null })),
    [owner],
  );
export const useBot = (name: string) => useQuery<DbBot>(() => fetchBot(name), [name]);
export const useUniverse = (slug: string) =>
  useQuery<DbUniverseWithCoins>(() => fetchUniverse(slug), [slug]);
export const useUniverseFilters = (universeId: string | null) =>
  useQuery<DbUniverseFilter[]>(
    () => (universeId ? fetchUniverseFilters(universeId) : Promise.resolve({ data: [], error: null })),
    [universeId],
  );
export const useFamilies = () => useQuery<DbFamily[]>(() => fetchFamilies());
export const useProfile = (handle: string) =>
  useQuery<DbProfile>(() => fetchProfile(handle), [handle]);
export const useMyFleets = (owner: string | null) =>
  useQuery<DbFleet[]>(
    () => (owner ? fetchMyFleets(owner) : Promise.resolve({ data: [], error: null })),
    [owner],
  );

export const useBacktests = (botId: string | null) =>
  useQuery<DbBacktest[]>(
    () => (botId ? fetchBacktests(botId) : Promise.resolve({ data: [], error: null })),
    [botId],
  );
export const useLatestBacktest = (botId: string | null) =>
  useQuery<DbBacktest | null>(
    () => (botId ? fetchLatestBacktest(botId) : Promise.resolve({ data: null, error: null })),
    [botId],
  );
export const useChecks = (backtestId: string | null) =>
  useQuery<DbCheck[]>(
    () => (backtestId ? fetchChecks(backtestId) : Promise.resolve({ data: [], error: null })),
    [backtestId],
  );
export const useConditions = (backtestId: string | null) =>
  useQuery<DbCondition[]>(
    () => (backtestId ? fetchConditions(backtestId) : Promise.resolve({ data: [], error: null })),
    [backtestId],
  );
export const useStrategyConditions = (botId: string | null) =>
  useQuery<DbStrategyCondition[]>(
    () => (botId ? fetchStrategyConditions(botId) : Promise.resolve({ data: [], error: null })),
    [botId],
  );
export const useBotVersions = (botId: string | null) =>
  useQuery<DbBotVersion[]>(
    () => (botId ? fetchBotVersions(botId) : Promise.resolve({ data: [], error: null })),
    [botId],
  );
export const usePlans = () => useQuery<DbPlan[]>(() => fetchPlans());

/** The whole lifecycle for one bot in a single settled read: its latest
 *  backtest, and that backtest's checks + conditions. `loading` is honest
 *  (an absent backtest resolves to `null`, not perpetual loading); bump
 *  `nonce` to re-poll while the engine worker is still running it. */
export interface BuildData {
  loading: boolean;
  backtest: DbBacktest | null;
  checks: DbCheck[];
  conditions: DbCondition[];
}
export function useBuildData(botId: string | null, nonce = 0): BuildData {
  const [state, setState] = useState<BuildData>({
    loading: true,
    backtest: null,
    checks: [],
    conditions: [],
  });
  useEffect(() => {
    let alive = true;
    if (!botId) {
      setState({ loading: false, backtest: null, checks: [], conditions: [] });
      return;
    }
    setState((s) => ({ ...s, loading: true }));
    (async () => {
      const { data: bt } = await fetchLatestBacktest(botId);
      let checks: DbCheck[] = [];
      let conditions: DbCondition[] = [];
      if (bt) {
        const [c, cond] = await Promise.all([fetchChecks(bt.id), fetchConditions(bt.id)]);
        checks = c.data ?? [];
        conditions = cond.data ?? [];
      }
      if (!alive) return;
      setState({ loading: false, backtest: bt ?? null, checks, conditions });
    })();
    return () => {
      alive = false;
    };
  }, [botId, nonce]);
  return state;
}

// ---- writes ----

/** Create a draft bot owned by the signed-in user. RLS (pf_bots_rw) requires
 *  owner = auth.uid(), so a live session is required. Lands in stage 'draft'. */
export const createDraftBot = (input: {
  name: string;
  owner: string;
  family_slug: string | null;
  universe_id: string | null;
  direction: string | null;
  params: Record<string, unknown>;
}) =>
  supabase
    .from("pf_bots")
    .insert({
      name: input.name,
      owner: input.owner,
      family_slug: input.family_slug,
      universe_id: input.universe_id,
      direction: input.direction,
      params: input.params,
      stage: "draft",
      market: "crypto",
      visibility: "results",
    })
    .select("id, name")
    .single();

/** Enqueue a backtest for a bot: the engine worker drains pending rows,
 *  runs the strategy over history, and writes results + Trials back. */
export const createBacktest = (input: { bot_id: string; universe_id: string | null }) =>
  supabase
    .from("pf_backtests")
    .insert({ bot_id: input.bot_id, universe_id: input.universe_id, status: "pending" })
    .select("id")
    .single();

/** Persist the weather gate — the conditions a bot is allowed to fight in. */
export const setConditionFilter = (bot_id: string, filter: Record<string, unknown> | null) =>
  supabase.from("pf_bots").update({ condition_filter: filter }).eq("id", bot_id);

/** Graduate a bot: assign it to a fleet, set visibility, and deploy it.
 *  RLS (pf_bots_rw) requires owner = auth.uid(). */
export const deployBot = (input: {
  bot_id: string;
  name: string;
  fleet_id: string;
  visibility: Visibility;
}) =>
  supabase
    .from("pf_bots")
    .update({
      name: input.name,
      fleet_id: input.fleet_id,
      visibility: input.visibility,
      stage: "deployed",
      launched_at: new Date().toISOString(),
    })
    .eq("id", input.bot_id)
    .select("id, name")
    .single();
