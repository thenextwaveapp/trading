// Mirrors the pf_* tables in Supabase (the product data layer).
// Runtime data (equity, trades, positions, curves, health) is NOT here —
// it comes from the live engine API, keyed by bot/variant `name`.

export type Stage =
  | "draft"
  | "backtesting"
  | "validation"
  | "conditions"
  | "ready"
  | "live"
  | "paused"
  | "archived";

export type Visibility = "private" | "results" | "public";
export type Direction = "short" | "long" | "both";

export interface DbBot {
  id: string;
  owner: string;
  fleet_id: string | null;
  name: string;
  slug: string | null;
  family_slug: string | null;
  universe_id: string | null;
  direction: Direction | null;
  engine: string | null;
  params: Record<string, unknown>;
  condition_filter: Record<string, unknown> | null;
  bt: number | null;
  note: string | null;
  description: string | null;
  market: string;
  version: number;
  copied_from: string | null;
  visibility: Visibility;
  status: string;
  stage: Stage;
  risk_weight: number;
  max_concurrent: number | null;
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
  validated_at: string | null;
  launched_at: string | null;
  builder?: { handle: string; avatar_color: string } | null;
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

// ---- research lifecycle ----

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
  status: "queued" | "running" | "done" | "failed";
  created_at: string;
}

export type CheckKey = "random" | "episodes" | "years" | "recent" | "unique";

export interface DbCheck {
  id: string;
  backtest_id: string;
  bot_id: string;
  key: CheckKey;
  label: string | null;
  status: "pending" | "checking" | "passed" | "failed";
  stat: number | null;
  threshold: number | null;
  detail: Record<string, unknown> | null;
  position: number;
}

export interface DbCondition {
  id: string;
  backtest_id: string;
  bot_id: string;
  volatility: "low" | "normal" | "high";
  btc_trend: "falling" | "flat" | "rising";
  return_per_trade: number | null;
  trades: number | null;
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
