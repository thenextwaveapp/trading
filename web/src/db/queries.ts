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
  DbSweep,
  DbSweepRun,
  DbUniverse,
  DbUniverseFilter,
  DbUniverseWithCoins,
  Stage,
  SweepAxis,
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

/** Bots currently moving through Compose -> Ready. Deployed bots leave this
 *  list; the sidebar shows the rung each in-progress build is standing on. */
export const fetchBuildBots = (owner: string) =>
  supabase
    .from("pf_bots")
    .select("*")
    .eq("owner", owner)
    .in("stage", ["draft", "training", "trials", "weather", "ready"])
    .order("created_at", { ascending: false });

/** One bot by id — the Build wizard's handle on what it is editing. */
export const fetchMyBot = (id: string) =>
  supabase
    .from("pf_bots")
    .select("*, builder:pf_profiles(handle, avatar_color)")
    .eq("id", id)
    .single();

/** Latest mark per deployed bot (one row per bot). */
export const fetchLatestMarks = () =>
  supabase
    .from("pf_bot_marks")
    .select("*")
    .order("t", { ascending: false });

/** Names are the public identity and unique per Builder. */
export const botNameTaken = async (
  owner: string,
  name: string,
  excludeId?: string,
) => {
  let q = supabase
    .from("pf_bots")
    .select("id")
    .eq("owner", owner)
    .eq("name", name)
    .limit(1);
  if (excludeId) q = q.neq("id", excludeId);
  const { data, error } = await q;
  return { taken: !!data?.length, error };
};

export const fetchUniverse = (slug: string) =>
  supabase
    .from("pf_universes")
    .select("*, pf_universe_coins(coin_symbol)")
    .eq("slug", slug)
    .single();

export const fetchUniverses = () =>
  supabase.from("pf_universes").select("*").order("slug");

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

export const fetchLatestDoneBacktest = async (botId: string) => {
  const { data, error } = await supabase
    .from("pf_backtests")
    .select("*")
    .eq("bot_id", botId)
    .order("created_at", { ascending: false })
    .limit(10);
  if (error) return { data: null, error };
  const rows = (data as DbBacktest[]) ?? [];
  const chosen =
    rows.find((r) => r.status === "done" && (r.equity_curve?.length ?? 0) > 0) ??
    rows.find((r) => r.status === "done") ??
    rows[0] ??
    null;
  return { data: chosen, error: null };
};

export const fetchLatestSweep = (botId: string) =>
  supabase
    .from("pf_sweeps")
    .select("*")
    .eq("bot_id", botId)
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();

export const fetchSweepRuns = (sweepId: string) =>
  supabase.from("pf_sweep_runs").select("*").eq("sweep_id", sweepId).order("position");

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
export const useBuildBots = (owner: string | null, nonce = 0) =>
  useQuery<DbBot[]>(
    () => (owner ? fetchBuildBots(owner) : Promise.resolve({ data: [], error: null })),
    [owner, nonce],
  );

/** One bot by id. Keeps its row while a poll refreshes it, but never leaks a
 *  previous bot's row when the id changes. */
export function useMyBot(id: string | null, nonce = 0): {
  data: DbBot | null;
  error: string | null;
  loading: boolean;
} {
  const [state, setState] = useState<{
    id: string | null;
    data: DbBot | null;
    error: string | null;
    loading: boolean;
  }>({ id: null, data: null, error: null, loading: !!id });

  useEffect(() => {
    let alive = true;
    if (!id) {
      setState({ id: null, data: null, error: null, loading: false });
      return;
    }
    setState((s) =>
      s.id === id
        ? { ...s, loading: s.data === null }
        : { id, data: null, error: null, loading: true },
    );
    fetchMyBot(id).then(({ data, error }) => {
      if (!alive) return;
      setState({
        id,
        data: (data as DbBot) ?? null,
        error: error?.message ?? null,
        loading: false,
      });
    });
    return () => {
      alive = false;
    };
  }, [id, nonce]);

  return { data: state.data, error: state.error, loading: state.loading };
}
export const useBot = (name: string) => useQuery<DbBot>(() => fetchBot(name), [name]);
export const useUniverse = (slug: string) =>
  useQuery<DbUniverseWithCoins>(() => fetchUniverse(slug), [slug]);
export const useUniverses = () =>
  useQuery<DbUniverse[]>(() => fetchUniverses());
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
    () => (botId ? fetchLatestDoneBacktest(botId) : Promise.resolve({ data: null, error: null })),
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
    // keep previous data visible while refreshing — no loading flash on poll
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

export interface SweepData {
  loading: boolean;
  sweep: DbSweep | null;
  runs: DbSweepRun[];
}

/** The latest sweep for a bot plus its result rows. Poll `nonce` while the
 *  worker is running; a bot change clears the previous bot's grid. */
export function useSweepData(botId: string | null, nonce = 0): SweepData {
  const [state, setState] = useState<
    SweepData & { botId: string | null }
  >({ botId: null, loading: !!botId, sweep: null, runs: [] });

  useEffect(() => {
    let alive = true;
    if (!botId) {
      setState({ botId: null, loading: false, sweep: null, runs: [] });
      return;
    }
    setState((s) =>
      s.botId === botId
        ? { ...s, loading: s.sweep === null }
        : { botId, loading: true, sweep: null, runs: [] },
    );
    (async () => {
      const { data: sweep } = await fetchLatestSweep(botId);
      let runs: DbSweepRun[] = [];
      if (sweep) {
        const { data } = await fetchSweepRuns(sweep.id);
        runs = (data as DbSweepRun[]) ?? [];
      }
      if (!alive) return;
      setState({
        botId,
        loading: false,
        sweep: (sweep as DbSweep) ?? null,
        runs,
      });
    })();
    return () => {
      alive = false;
    };
  }, [botId, nonce]);

  return { loading: state.loading, sweep: state.sweep, runs: state.runs };
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
  spec?: Record<string, unknown> | null;
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
      spec: input.spec ?? null,
      stage: "draft",
      market: "crypto",
      visibility: "private", // private by default — you choose when to publish
    })
    .select("id, name")
    .single();

/** Edit a composed bot. The old backtest and weather gate no longer describe
 *  this Setup, so clear them and send the bot back to Draft until re-trained.
 *  RLS (pf_bots_rw) requires owner = auth.uid(). */
export const updateDraftBot = (input: {
  id: string;
  name: string;
  family_slug: string | null;
  universe_id: string | null;
  direction: string | null;
  params: Record<string, unknown>;
  spec?: Record<string, unknown> | null;
}) =>
  supabase
    .from("pf_bots")
    .update({
      name: input.name,
      family_slug: input.family_slug,
      universe_id: input.universe_id,
      direction: input.direction,
      params: input.params,
      spec: input.spec === undefined ? null : input.spec,
      stage: "draft",
      bt: null,
      validated_at: null,
      condition_filter: null,
    })
    .eq("id", input.id)
    .select("id, name")
    .single();

/** Move a bot along the ladder (training -> trials -> weather -> ready). */
export const setBotStage = (bot_id: string, stage: Stage) =>
  supabase.from("pf_bots").update({ stage }).eq("id", bot_id);

/** Close the Weather step: persist the regime gate and graduate to Ready. */
export const saveWeatherGate = (
  bot_id: string,
  filter: Record<string, unknown> | null,
) =>
  supabase
    .from("pf_bots")
    .update({
      condition_filter: filter,
      stage: "ready",
      validated_at: new Date().toISOString(),
    })
    .eq("id", bot_id);

/** A Builder needs at least one fleet to deploy into. The signup trigger seeds
 *  one; this is the fallback if it is missing. */
export const createFleet = (owner: string, name = "My Fleet") =>
  supabase
    .from("pf_fleets")
    .insert({
      owner,
      name,
      color: "#3a81d7",
      budget_per_bot: 10_000,
      market: "crypto",
      check_interval_min: 15,
      status: "active",
      kill_switch_pct: -5,
      benchmark_pct: 2,
    })
    .select("*")
    .single();

/** Enqueue a backtest for a bot: the engine worker drains pending rows,
 *  runs the strategy over history, and writes results + Trials back. */
export const createBacktest = (input: { bot_id: string; universe_id: string | null }) =>
  supabase
    .from("pf_backtests")
    .insert({ bot_id: input.bot_id, universe_id: input.universe_id, status: "pending" })
    .select("id")
    .single();

/** Enqueue a parameter grid. The engine worker expands it and writes one
 *  pf_sweep_runs row per point; RLS follows the parent bot's owner. */
export const createSweep = (input: {
  bot_id: string;
  universe_id: string | null;
  universe_slug: string;
  spec: Record<string, unknown>;
  axes: SweepAxis[];
}) =>
  supabase
    .from("pf_sweeps")
    .insert({
      bot_id: input.bot_id,
      universe_id: input.universe_id,
      universe_slug: input.universe_slug,
      spec: input.spec,
      axes: input.axes,
      status: "pending",
    })
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

/** Permanently delete a bot owned by the signed-in user (cascades to child rows). */
export const deleteBot = (bot_id: string) =>
  supabase.from("pf_bots").delete().eq("id", bot_id);
