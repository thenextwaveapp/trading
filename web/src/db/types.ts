// Mirrors the pf_* tables in Supabase.
// Runtime data (equity, trades, positions, curves, health) is not here — it
// comes from the live engine API, keyed by bot/variant `name`.

export type Stage =
  | "draft"
  | "training"
  | "trials"
  | "weather"
  | "ready"
  | "deployed";

export type Visibility = "private" | "results" | "public";
export type Direction = "short" | "long" | "both";

export interface DbBotMark {
  id: number;
  bot_id: string;
  t: number;
  equity: number;
  ret: number | null;
  open_json: unknown;
  closed: number | null;
  win: number | null;
  paused: boolean;
  kill: boolean;
  log_tail: string | null;
}

export interface DbBot {
  id: string;
  owner: string;
  fleet_id: string | null;
  name: string;
  slug: string | null;
  family_slug: string | null;
  universe_id: string | null;
  direction: Direction | null;
  params: Record<string, unknown>;
  condition_filter: Record<string, unknown> | null;
  spec: Record<string, unknown> | null;
  bt: number | null;
  note: string | null;
  description: string | null;
  market: string;
  version: number;
  copied_from: string | null;
  visibility: Visibility;
  stage: Stage;
  created_at: string | null;
  updated_at: string | null;
  validated_at: string | null;
  launched_at: string | null;
  builder?: {
    handle: string;
    avatar_color: string;
    profile_public?: boolean;
    bots_on_leaderboard?: boolean;
  } | null;
}

export interface DbUniverse {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  owner: string | null;
}

export interface DbUniverseWithCoins extends DbUniverse {
  pf_universe_coins: { coin_symbol: string }[];
}

export interface DbUniverseFilter {
  id: string;
  universe_id: string;
  type: "market_cap" | "volume" | "listing_age" | "exclusion";
  op: string | null;
  min_val: number | null;
  max_val: number | null;
  threshold: number | null;
  unit: string | null;
  value: string | null;
  position: number;
}

export interface DbCoin {
  symbol: string;
  binance_symbol: string;
  name: string | null;
}

export interface DbProfile {
  id: string;
  handle: string;
  display_name: string | null;
  avatar_color: string;
  avatar_url: string | null;
  bio: string | null;
  email: string | null;
  tz: string | null;
  currency: string | null;
  profile_public: boolean;
  bots_on_leaderboard: boolean;
  default_bot_visibility: Visibility;
  onboarding_step: number;
  onboarding_checklist: Record<string, unknown>;
  onboarded_at: string | null;
}

export interface DbFamily {
  slug: string;
  label: string;
  description: string | null;
  direction: Direction | null;
  engine: string | null;
  thesis: string | null;
  default_params: Record<string, unknown> | null;
}

export interface DbFleet {
  id: string;
  owner: string;
  name: string;
  color: string;
  budget_per_bot: number;
  market: string;
  check_interval_min: number;
  status: string;
  kill_switch_pct: number | null;
  benchmark_pct: number | null;
  description: string | null;
}

// ---- build lifecycle ----

export interface DbBacktest {
  id: string;
  bot_id: string;
  universe_id: string | null;
  window_start: string | null;
  window_end: string | null;
  initial_capital: number;
  final_value: number | null;
  total_return: number | null;
  trades: number | null;
  win_rate: number | null;
  wins: number | null;
  losses: number | null;
  avg_trade: number | null;
  net_per_trade: number | null;
  max_drawdown: number | null;
  drawdown_recovery_days: number | null;
  longest_gap_days: number | null;
  spread_vs_standin: number | null;
  episodes: number | null;
  by_year: Record<string, number> | null;
  equity_curve: [number, number][] | null;
  notable: Record<string, unknown> | null;
  expectations: Record<string, unknown> | null;
  cost_note: string | null;
  params: Record<string, unknown> | null;
  status: "pending" | "running" | "done" | "error";
  created_at: string;
}

export type CheckKey = "cost_stress" | "entry_delay" | "placebo";

export interface DbCheck {
  id: string;
  backtest_id: string;
  bot_id: string;
  key: CheckKey;
  label: string | null;
  status: "pending" | "pass" | "fail";
  stat: number | null;
  threshold: number | null;
  detail: Record<string, unknown> | null;
  position: number;
}

export interface SweepAxis {
  path: string;
  values: unknown[];
}

export interface SweepStats {
  n: number;
  win_rate: number;
  net_pct_per_trade: number;
  total_net_pct: number;
  final_equity: number;
  max_drawdown: number;
}

export interface DbSweep {
  id: string;
  bot_id: string;
  universe_id: string | null;
  universe_slug: string | null;
  spec: Record<string, unknown>;
  axes: SweepAxis[];
  window_start: string | null;
  window_end: string | null;
  run_count: number;
  completed_count: number;
  status: "pending" | "running" | "done" | "error";
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface DbSweepRun {
  id: string;
  sweep_id: string;
  position: number;
  label: string;
  changes: Record<string, unknown>;
  stats: SweepStats | null;
  issues: { id?: string; label?: string; reason?: string; blocking?: boolean }[] | null;
  error: string | null;
  created_at: string;
}

export interface DbCondition {
  id: string;
  backtest_id: string;
  bot_id: string;
  volatility: "low" | "normal" | "high";
  btc_trend: "falling" | "flat" | "rising";
  return_per_trade: number | null;
  trades: number | null;
  vol_lo: number | null;
  vol_hi: number | null;
  is_current: boolean;
  selected: boolean;
}

export interface DbStrategyCondition {
  id: string;
  bot_id: string;
  kind: "entry" | "exit";
  type: string;
  measure: string | null;
  direction: string | null;
  amount: number | null;
  timeframe: string | null;
  timing: string | null;
  candles: string | null;
  modifiers: unknown;
  raw: string | null;
  position: number;
}

export interface DbBotVersion {
  id: string;
  bot_id: string;
  version: number;
  params: Record<string, unknown>;
  change_note: string | null;
  checks_passed: number | null;
  checks_total: number | null;
  fingerprint: string | null;
  status: "active" | "archived";
  created_at: string;
}

// ---- challenges ----

export type ChallengeStatus = "draft" | "open" | "sealed" | "live" | "closed";
export type Judge =
  | "return"
  | "calmar"
  | "profit_factor"
  | "low_drawdown"
  | "fewest_trades_positive"
  | "median_distance";

export interface ChallengeLockSet {
  holes: string[];
  predicates: Record<string, unknown>[];
}

export interface DbChallenge {
  id: string;
  slug: string;
  title: string;
  blurb: string | null;
  created_by: string | null;
  market: string;
  template: Record<string, unknown>;
  lock_set: ChallengeLockSet;
  judge: Judge;
  judge_cfg: Record<string, unknown>;
  seal: boolean;
  season: number | null;
  week: number | null;
  build_open: string | null;
  build_close: string | null;
  market_open: string | null;
  market_close: string | null;
  status: ChallengeStatus;
  created_at: string;
  updated_at: string;
}

export interface DbChallengeStanding {
  id: string;
  challenge_id: string;
  bot_id: string;
  place: number | null;
  eligible: boolean;
  score: number | null;
  total_return: number | null;
  max_drawdown: number | null;
  trades: number | null;
  created_at: string;
}

/** The safe public projection of a bot (pf_bot_cards view): identity + record,
 *  never the Setup. Used for a sealed challenge entry whose spec stays hidden. */
export interface DbBotCard {
  id: string;
  owner: string;
  name: string;
  slug: string | null;
  market: string;
  stage: Stage;
  visibility: Visibility;
  challenge_id: string | null;
  bt: number | null;
  created_at: string | null;
}

// ---- market discovery ----

export interface DbMarketRow {
  symbol: string;      // BTCUSDT
  base: string;        // BTC
  market: string;      // crypto
  price: number | null;
  change_pct: number | null;   // 24h
  quote_volume: number | null; // 24h, quote ccy
  high: number | null;
  low: number | null;
  trades: number | null;
  updated_at: string;
  // enrichment (CoinGecko); null until the feed resolves it
  name: string | null;            // Bitcoin
  logo: string | null;            // icon url
  market_cap: number | null;
  market_cap_rank: number | null;
  circ_supply: number | null;
  ath: number | null;
}

export interface DbEvent {
  id: string;
  ts: string;
  type: "entered" | "exited" | "followed" | "copied" | "kill_switch" | string;
  bot_id: string | null;
  bot_name: string | null;
  market: string | null;
  actor: string | null;
  actor_handle: string | null;
  target_builder: string | null;
  visibility: string;
  payload: Record<string, unknown>;
}

export interface DbNews {
  id: string;
  url: string;
  title: string;
  source: string | null;
  published_at: string | null;
  created_at: string;
}

// ---- account ----

export interface DbPlan {
  key: string;
  label: string;
  price_monthly: number;
  max_bots: number | null;
  max_fleets: number | null;
  max_backtests_monthly: number | null;
  features: Record<string, unknown> | null;
  position: number;
}
