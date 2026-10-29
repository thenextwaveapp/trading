import { useEffect, useState } from "react";
import { supabase } from "./supabase";
import type {
  DbBacktest,
  DbBot,
  DbBotCard,
  DbBotVersion,
  DbChallenge,
  DbChallengeStanding,
  DbCheck,
  DbCondition,
  DbEvent,
  DbFamily,
  DbFleet,
  DbMarketRow,
  DbNews,
  DbPlan,
  DbProfile,
  DbStrategyCondition,
  DbSweep,
  DbSweepRun,
  DbCoin,
  DbUniverse,
  DbUniverseFilter,
  DbUniverseWithCoins,
  Stage,
  SweepAxis,
  Visibility,
} from "./types";

/** Process-wide stale-while-revalidate cache: a revisited page renders its last
 *  result instantly (no loading flash), then refreshes in the background. */
const qcache = new Map<string, unknown>();
export function invalidateQuery(prefix: string) {
  for (const k of qcache.keys()) if (k.startsWith(prefix)) qcache.delete(k);
}

/** Tiny async-query hook. Pass a stable `key` to enable the cache. */
export function useQuery<T>(
  run: () => PromiseLike<{ data: T | null; error: { message: string } | null }>,
  deps: unknown[] = [],
  key?: string,
): { data: T | null; error: string | null; loading: boolean } {
  const [data, setData] = useState<T | null>(
    () => (key && qcache.has(key) ? (qcache.get(key) as T) : null),
  );
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    run().then(({ data, error }) => {
      if (!alive) return;
      if (error) setError(error.message);
      else {
        setData(data);
        if (key && data != null) qcache.set(key, data);
      }
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
    .select("*, builder:pf_profiles(handle, avatar_color, profile_public, bots_on_leaderboard)")
    .neq("visibility", "private")
    .order("name");

export const fetchBot = (name: string) =>
  supabase
    .from("pf_bots")
    .select("*, builder:pf_profiles(handle, avatar_color, profile_public, bots_on_leaderboard)")
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

export const fetchPublicProfiles = () =>
  supabase.from("pf_profiles").select("*").eq("profile_public", true).order("handle");

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

export const useBots = () => useQuery<DbBot[]>(() => fetchBots(), [], "bots");
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
export const useBot = (name: string) => useQuery<DbBot>(() => fetchBot(name), [name], "bot:" + name);
export const useUniverse = (slug: string) =>
  useQuery<DbUniverseWithCoins>(() => fetchUniverse(slug), [slug], "universe:" + slug);
export const useUniverses = () =>
  useQuery<DbUniverse[]>(() => fetchUniverses(), [], "universes");
export const useUniverseFilters = (universeId: string | null) =>
  useQuery<DbUniverseFilter[]>(
    () => (universeId ? fetchUniverseFilters(universeId) : Promise.resolve({ data: [], error: null })),
    [universeId],
  );
export const fetchCoins = (market: string) =>
  supabase.from("pf_coins").select("symbol, binance_symbol, name, market").eq("market", market).order("symbol");
/** Instruments that belong to a market — the Builder's custom-universe picker. */
export const useCoins = (market: string) =>
  useQuery<DbCoin[]>(() => fetchCoins(market), [market], "coins:" + market);

/** Create an owned universe from a hand-picked set of coins. Backtest (by slug)
 *  and live (by universe_id) both resolve pf_universe_coins, so a custom subset
 *  trades exactly as it backtests. `saved` controls whether it's reusable in the
 *  dropdown; an unsaved one is a throwaway tied to a single bot. */
export const createUniverse = async (opts: {
  owner: string;
  name: string;
  market: string;
  coins: string[];
  saved: boolean;
}): Promise<{ id: string; slug: string } | null> => {
  const base =
    (opts.name || "custom").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 24) || "custom";
  const slug = `${base}-${crypto.randomUUID().slice(0, 8)}`;
  const { data, error } = await supabase
    .from("pf_universes")
    .insert({
      owner: opts.owner,
      name: opts.name?.trim() || "Custom universe",
      slug,
      market: opts.market,
      saved: opts.saved,
    })
    .select("id, slug")
    .single();
  if (error || !data) return null;
  if (opts.coins.length) {
    const rows = opts.coins.map((coin_symbol) => ({ universe_id: data.id, coin_symbol }));
    const { error: coinErr } = await supabase.from("pf_universe_coins").insert(rows);
    if (coinErr) {
      await supabase.from("pf_universes").delete().eq("id", data.id); // no orphan empty universe
      return null;
    }
  }
  return { id: data.id, slug: data.slug };
};

/** Replace an owned universe's coins and metadata (name/saved/market). */
export const updateUniverse = async (
  id: string,
  patch: { name?: string; saved?: boolean; market?: string; coins?: string[] },
): Promise<boolean> => {
  const meta: Record<string, unknown> = {};
  if (patch.name !== undefined) meta.name = patch.name.trim() || "Custom universe";
  if (patch.saved !== undefined) meta.saved = patch.saved;
  if (patch.market !== undefined) meta.market = patch.market;
  if (Object.keys(meta).length) {
    const { error } = await supabase.from("pf_universes").update(meta).eq("id", id);
    if (error) return false;
  }
  if (patch.coins) {
    await supabase.from("pf_universe_coins").delete().eq("universe_id", id);
    if (patch.coins.length) {
      const { error } = await supabase
        .from("pf_universe_coins")
        .insert(patch.coins.map((coin_symbol) => ({ universe_id: id, coin_symbol })));
      if (error) return false;
    }
  }
  return true;
};

export const useFamilies = () => useQuery<DbFamily[]>(() => fetchFamilies(), [], "families");
export const useProfile = (handle: string) =>
  useQuery<DbProfile>(() => fetchProfile(handle), [handle], "profile:" + handle);
export const usePublicProfiles = () =>
  useQuery<DbProfile[]>(() => fetchPublicProfiles(), [], "profiles");
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
export const usePlans = () => useQuery<DbPlan[]>(() => fetchPlans(), [], "plans");

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
  visibility?: Visibility;
  copied_from?: string | null;
  challenge_id?: string | null;
  market?: string;
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
      copied_from: input.copied_from ?? null,
      challenge_id: input.challenge_id ?? null,
      stage: "draft",
      market: input.market ?? (input.spec?.market === "equity" ? "stocks" : "crypto"),
      visibility: input.visibility ?? "private",
    })
    .select("id, name")
    .single();

/** Clone a bot into the signed-in Builder's roster as a Draft to edit in Compose. */
export const copyBotToDraft = async (
  source: DbBot,
  owner: string,
  visibility: Visibility = "private",
) => {
  const baseName = `${source.name} copy`.slice(0, 28);
  let candidate = baseName;
  for (let n = 2; n <= 20; n++) {
    const check = await botNameTaken(owner, candidate);
    if (!check.taken) break;
    candidate = `${baseName} ${n}`;
  }
  const clonedSpec =
    source.spec && typeof source.spec === "object"
      ? { ...(source.spec as Record<string, unknown>), name: candidate }
      : null;
  return createDraftBot({
    name: candidate,
    owner,
    family_slug: source.family_slug,
    universe_id: source.universe_id,
    direction: source.direction,
    params: { ...(source.params ?? {}) },
    spec: clonedSpec,
    visibility,
    copied_from: source.id,
  });
};

/** Update a bot's visibility setting ('private' | 'results' | 'public'). */
export const setBotVisibility = (bot_id: string, visibility: Visibility) =>
  supabase.from("pf_bots").update({ visibility }).eq("id", bot_id);

/** Update visibility across all bots owned by a builder. */
export const setAllMyBotsVisibility = (owner: string, visibility: Visibility) =>
  supabase.from("pf_bots").update({ visibility }).eq("owner", owner);

/** Upload a builder's avatar image to the public `avatars` bucket (path scoped
 *  to their uid so RLS allows it), then save the public URL on the profile. */
export const uploadAvatar = async (userId: string, file: File) => {
  const ext = (file.name.split(".").pop() || "png").toLowerCase();
  const path = `${userId}/avatar.${ext}`;
  const up = await supabase.storage.from("avatars").upload(path, file, {
    upsert: true,
    cacheControl: "3600",
    contentType: file.type || undefined,
  });
  if (up.error) return { url: null, error: up.error };
  const { data } = supabase.storage.from("avatars").getPublicUrl(path);
  const url = `${data.publicUrl}?v=${Date.now()}`; // cache-bust on replace
  const { error } = await supabase.from("pf_profiles").update({ avatar_url: url }).eq("id", userId);
  return { url, error };
};

/** Update the signed-in Builder's profile and privacy settings. */
export const updateBuilderProfile = (
  id: string,
  changes: Partial<
    Pick<
      DbProfile,
      | "display_name"
      | "bio"
      | "avatar_color"
      | "profile_public"
      | "bots_on_leaderboard"
      | "default_bot_visibility"
    >
  >,
) => supabase.from("pf_profiles").update(changes).eq("id", id);

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
      market: input.spec?.market === "equity" ? "stocks" : "crypto",
      stage: "draft",
      bt: null,
      validated_at: null,
      condition_filter: null,
    })
    .eq("id", input.id)
    .select("id, name")
    .single();

/** Silent auto-save while moving back and forth across Build steps.
 *  Preserves stage/bt/condition_filter unless explicitly reset. */
export const autosaveBot = (input: {
  id: string;
  name: string;
  family_slug: string | null;
  universe_id: string | null;
  direction: string | null;
  params: Record<string, unknown>;
  spec?: Record<string, unknown> | null;
  visibility?: Visibility;
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
      market: input.spec?.market === "equity" ? "stocks" : "crypto",
      ...(input.visibility ? { visibility: input.visibility } : {}),
    })
    .eq("id", input.id)
    .select("id, name")
    .single();

/** Auto-save deploy preferences (name, fleet, visibility) on Step 5. */
export const autosaveDeployPrefs = (input: {
  id: string;
  name: string;
  fleet_id: string | null;
  visibility: Visibility;
}) =>
  supabase
    .from("pf_bots")
    .update({
      name: input.name,
      fleet_id: input.fleet_id,
      visibility: input.visibility,
    })
    .eq("id", input.id);
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

/** Queue an owner action on an open position (close / adjust stop / adjust TP).
 *  The engine drains pending rows and applies them on its next cycle. */
export const queuePositionAction = (input: {
  bot_id: string;
  ticker: string;
  action: "close" | "set_stop" | "set_tp";
  value?: number | null;
}) =>
  supabase.from("pf_position_actions").insert({
    bot_id: input.bot_id, ticker: input.ticker, action: input.action,
    value: input.value ?? null,
  });

/** Permanently delete a bot owned by the signed-in user (cascades to child rows). */
export const deleteBot = (bot_id: string) =>
  supabase.from("pf_bots").delete().eq("id", bot_id);

// ---- market discovery ----

/** Live market snapshot the engine writes (pf_market_snapshot). Most-traded
 *  first; sorting/filtering for the board is done client-side. */
export const fetchMarketSnapshot = (market = "crypto") =>
  supabase.from("pf_market_snapshot").select("*").eq("market", market)
    .order("quote_volume", { ascending: false });

export const useMarket = (market = "crypto") =>
  useQuery<DbMarketRow[]>(() => fetchMarketSnapshot(market), [market], "market:" + market);

/** Builders the signed-in user follows (builder ids). */
export const fetchMyFollows = (follower: string) =>
  supabase.from("pf_follows").select("builder").eq("follower", follower);
export const useMyFollows = (follower: string | null) =>
  useQuery<{ builder: string }[]>(
    () => (follower ? fetchMyFollows(follower) : Promise.resolve({ data: [], error: null })),
    [follower],
    follower ? "follows:" + follower : undefined,
  );
export const followBuilder = (follower: string, builder: string) =>
  supabase.from("pf_follows").insert({ follower, builder });
export const unfollowBuilder = (follower: string, builder: string) =>
  supabase.from("pf_follows").delete().eq("follower", follower).eq("builder", builder);

/** The activity feed — trade/copy/follow events, newest first. RLS hides
 *  private actors' events. */
export const fetchEvents = (limit = 60) =>
  supabase.from("pf_events").select("*").order("ts", { ascending: false }).limit(limit);

export const useEvents = (limit = 60) =>
  useQuery<DbEvent[]>(() => fetchEvents(limit), [limit], "events:" + limit);

/** Latest crypto news headlines (pf_news), newest first. */
export const fetchNews = (limit = 40) =>
  supabase.from("pf_news").select("*").order("published_at", { ascending: false }).limit(limit);

export const useNews = (limit = 40) =>
  useQuery<DbNews[]>(() => fetchNews(limit), [limit], "news:" + limit);

export const fetchMarketRow = (symbol: string) =>
  supabase.from("pf_market_snapshot").select("*").eq("symbol", symbol).maybeSingle();

export const useMarketRow = (symbol: string) =>
  useQuery<DbMarketRow | null>(() => fetchMarketRow(symbol), [symbol], "marketrow:" + symbol);

// ---- challenges ----

/** Every challenge that has left draft (RLS also shows the author their own). */
export const fetchChallenges = () =>
  supabase.from("pf_challenges").select("*").order("created_at", { ascending: false });

export const fetchChallenge = (slug: string) =>
  supabase.from("pf_challenges").select("*").eq("slug", slug).single();

/** A challenge's entrants as safe cards (identity + record, never the Setup).
 *  Reads the pf_bot_cards view so a sealed entry's spec stays hidden. */
export const fetchChallengeEntries = (challengeId: string) =>
  supabase.from("pf_bot_cards").select("*").eq("challenge_id", challengeId);

/** The settled board: one row per entry, winner first (ineligible last). */
export const fetchStandings = (challengeId: string) =>
  supabase
    .from("pf_challenge_standings")
    .select("*")
    .eq("challenge_id", challengeId)
    .order("place", { ascending: true, nullsFirst: false });

export const useChallenges = () => useQuery<DbChallenge[]>(() => fetchChallenges(), [], "challenges");
export const useChallenge = (slug: string) =>
  useQuery<DbChallenge>(() => fetchChallenge(slug), [slug], "challenge:" + slug);

export interface ChallengeBoard {
  loading: boolean;
  entries: DbBotCard[];
  standings: DbChallengeStanding[];
}

/** Entrants (cards) + standings for one challenge in a single settled read. */
export function useChallengeBoard(challengeId: string | null, nonce = 0): ChallengeBoard {
  const [state, setState] = useState<ChallengeBoard>({
    loading: !!challengeId,
    entries: [],
    standings: [],
  });
  useEffect(() => {
    let alive = true;
    if (!challengeId) {
      setState({ loading: false, entries: [], standings: [] });
      return;
    }
    (async () => {
      const [e, st] = await Promise.all([
        fetchChallengeEntries(challengeId),
        fetchStandings(challengeId),
      ]);
      if (!alive) return;
      setState({
        loading: false,
        entries: (e.data as DbBotCard[]) ?? [],
        standings: (st.data as DbChallengeStanding[]) ?? [],
      });
    })();
    return () => {
      alive = false;
    };
  }, [challengeId, nonce]);
  return state;
}

/** Enter a challenge: Copy its locked template into a Draft stamped with the
 *  challenge_id, to tune the one open hole in Compose. The engine re-checks the
 *  lock-set on save, and the DB freezes the Setup once the window closes. */
export const enterChallenge = async (challenge: DbChallenge, owner: string) => {
  const base = `${challenge.title} entry`.slice(0, 28);
  let candidate = base;
  for (let n = 2; n <= 20; n++) {
    const check = await botNameTaken(owner, candidate);
    if (!check.taken) break;
    candidate = `${base} ${n}`;
  }
  const tmpl: Record<string, unknown> =
    challenge.template && typeof challenge.template === "object"
      ? { ...(challenge.template as Record<string, unknown>), name: candidate }
      : { name: candidate };
  return createDraftBot({
    name: candidate,
    owner,
    family_slug: null,
    universe_id: null,
    direction: (tmpl.side as string) ?? null,
    params: {},
    spec: tmpl,
    visibility: "private",
    challenge_id: challenge.id,
  });
};
