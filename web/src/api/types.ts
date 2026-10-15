// Mirrors fleet_dashboard.py payload() — the single source of truth.

export type Group = "short" | "long" | "both";
export type Side = "short" | "long";
/** exit reason codes used in trade logs */
export type Kind = "sl" | "time" | "tp" | "manual" | "trail" | string;

export interface Position {
  variant: string;
  ticker: string;
  side: Side;
  entry: number;
  px: number | null;
  upct: number | null; // fraction, e.g. 0.023
  upnl: number | null; // dollars
  stop: number;
  room: number | null; // fraction to stop
  notional: number;
  t_sig: number; // ms
  tp: number | null;
  exits_at: number; // ms
}

export interface Trade {
  variant: string;
  ticker: string;
  t_sig: number;
  entry: number;
  stop: number;
  exit_t: number;
  kind: Kind;
  net: number; // fraction
  pnl: number; // dollars
  notional: number;
  equity_after: number;
}

export interface Variant {
  name: string;
  params: string;
  equity: number;
  ret: number; // percent
  open: Position[];
  closed: number;
  win: number | null; // percent
  avg: number | null; // percent, avg net
  bt: number | null; // percent, backtest net
  curve: [number, number][]; // [t_ms, equity]
  kill: boolean;
  group: Group | null;
  note: string | null;
  cfg: Record<string, unknown> | null;
}

export interface Hero {
  base_pnl: number;
  base_ret: number;
  base_closed: number;
  base_avg: number | null;
  bench: number;
  fleet_pnl: number;
  unreal: number;
  week_pnl: number;
  closed: number;
}

export interface Payload {
  now: number;
  start: number;
  gate: { bear: boolean | null };
  hero: Hero;
  variants: Variant[];
  strats: Record<string, { label: string; variants: string[] }>;
  positions: Position[];
  trades: Trade[];
  log: string[];
  running: boolean | null;
  loaded: boolean;
  paused: boolean;
  health: { status: "green" | "amber" | "red"; msg: string };
  ntfy: string;
  state_age_s: number | null;
  symbols: Record<string, string>; // ticker -> binance symbol
  _source?: "upstream" | "local" | "local-stale";
}

export interface Candle {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
}
