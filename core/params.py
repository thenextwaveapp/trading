"""One typed registry for every strategy parameter, plus engine capabilities.

This is the product's source of truth for the Builder: controls, defaults,
ranges, grouping, and which engine can actually execute a choice. The web
catalog is generated from it by core/export_catalog.py.

Design rule: the registry describes capability, not taste. If the engine can
execute a value, it is exposed. If it cannot, the value stays visible with a
reason instead of silently doing nothing. No parameter is "advanced-only" and
nothing is blocked by an arbitrary bucket boundary.
"""
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .timeframes import TIMEFRAMES

TARGETS = ("backtest", "live")
STOP_MODES = ("none", "hh", "dstop", "sig", "trail")


def _opt(value: str, label: str, *, backtest: bool = True,
         live: bool = True, status: str = "ok", reason: str = "") -> dict:
    return {"value": value, "label": label, "backtest": backtest,
            "live": live, "status": status, "reason": reason}


def _day(value: int, label: str) -> dict:
    return {"value": value, "label": label}


@dataclass(frozen=True)
class Param:
    key: str
    label: str
    kind: str
    default: Any
    group: str
    help: str = ""
    min: float | None = None
    max: float | None = None
    step: float | None = None
    unit: str | None = None
    percent: bool = False
    choices: tuple[Any, ...] = ()
    options: tuple[dict, ...] = ()
    visible_if: dict | None = None
    status: str = "ok"
    backtest: bool = True
    live: bool = False
    sweep: bool = True
    in_default: bool = True
    reason: str = ""

    def json(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "kind": self.kind,
            "default": deepcopy(self.default),
            "group": self.group,
            "help": self.help,
            "min": self.min,
            "max": self.max,
            "step": self.step,
            "unit": self.unit,
            "percent": self.percent,
            "choices": list(self.choices),
            "options": deepcopy(list(self.options)),
            "visible_if": deepcopy(self.visible_if),
            "status": self.status,
            "backtest": self.backtest,
            "live": self.live,
            "sweep": self.sweep,
            "in_default": self.in_default,
            "reason": self.reason,
        }


GROUPS = (
    {"id": "direction", "label": "Direction"},
    {"id": "market", "label": "Market"},
    {"id": "entry", "label": "Entry"},
    {"id": "timing", "label": "Timing"},
    {"id": "exit", "label": "Exit"},
    {"id": "sizing", "label": "Sizing"},
    {"id": "filters", "label": "Filters"},
)

PARAMS = (
    Param(
        "side", "Side", "enum", "short", "direction",
        help="Direction of the position taken on a signal.",
        options=(
            _opt("short", "Short"),
            _opt("long", "Long"),
            _opt("both", "Both"),
        ),
        live=True,
    ),
    Param(
        "market", "Market", "enum", "crypto_perp", "market",
        help="Instrument model; indicator availability is checked by parse().",
        live=True, sweep=True,
    ),
    Param(
        "timeframe", "Candle size", "enum", "15m", "market",
        help="Bar size used for signals, stops, holds and exits. Every "
             "backtest, sweep and live bot runs on the selected tape.",
        options=tuple(
            _opt(value, label)
            for value, label, _ms in TIMEFRAMES
        ) + (
            _opt(
                "1M", "1 month",
                backtest=False, live=False, status="unsupported",
                reason="Calendar months are not fixed-width, so the engine "
                       "cannot apply its gapless-bar and timestamp checks. "
                       "Use 1w or a fixed number of days instead.",
            ),
        ),
        live=True,
    ),
    Param(
        "universe", "Universe", "string", "fleet-60", "market",
        help="Ticker set the strategy is evaluated over.",
        live=True,
    ),
    Param(
        "fresh", "Fresh only", "bool", False, "entry",
        help="Fire only on the first bar a condition becomes true.",
        live=True,
    ),
    Param(
        "entry", "Entry conditions", "condition",
        {"logic": "AND", "children": []}, "entry",
        help="Composable condition tree evaluated on each closed bar.",
        live=True,
    ),
    Param(
        "timing.hours_utc", "Hours (UTC)", "int_list", [], "timing",
        help="UTC hours when a signal may fire, measured at bar close. "
             "Empty means every hour.",
        min=0, max=23, step=1, unit="hour", choices=tuple(range(24)),
        live=True,
    ),
    Param(
        "timing.days_utc", "Days (UTC)", "int_list", [], "timing",
        help="UTC weekdays when a signal may fire, Monday=0. "
             "Empty means every day.",
        min=0, max=6, step=1, choices=(0, 1, 2, 3, 4, 5, 6),
        options=(
            _day(0, "Mon"), _day(1, "Tue"), _day(2, "Wed"),
            _day(3, "Thu"), _day(4, "Fri"), _day(5, "Sat"),
            _day(6, "Sun"),
        ),
        live=True,
    ),
    Param(
        "timing.dates", "Dates (UTC)", "date_list", [], "timing",
        help="Specific UTC calendar dates a signal may fire, measured at bar "
             "close. Each entry is an ISO date \"YYYY-MM-DD\" or an inclusive "
             "range \"YYYY-MM-DD/YYYY-MM-DD\". Empty means every date.",
        in_default=False, live=True,
    ),
    Param(
        "exit.time_bars", "Max hold", "int", 16, "exit",
        help="Bars from entry to the time exit.",
        min=1, step=1, unit="bar", live=True,
    ),
    Param(
        "exit.stop.mode", "Stop mode", "enum", "hh", "exit",
        help="Stop construction from the signal window or entry.",
        options=(
            _opt("none", "None (time only)"),
            _opt("hh", "Signal-window extreme"),
            _opt("dstop", "Fixed % disaster stop"),
            _opt("sig", "Signal-window midpoint stop"),
            _opt(
                "trail", "Legacy trailing mode",
                backtest=False, live=False, status="unsupported",
                reason="stop.mode='trail' was displayed but never implemented. "
                       "Use exit.trailing instead.",
            ),
        ),
        live=True,
    ),
    Param(
        "exit.stop.window", "Stop window", "int", 16, "exit",
        help="Signal-window bars used by hh and sig.",
        min=1, step=1, unit="bar",
        visible_if={"path": "exit.stop.mode", "in": ["hh", "sig"]},
        live=True,
    ),
    Param(
        "exit.stop.param", "Stop parameter", "float", 0.0, "exit",
        help="Buffer for hh/sig or distance for dstop, in percent.",
        step=0.0001, unit="%", percent=True,
        visible_if={"path": "exit.stop.mode", "in": ["hh", "sig", "dstop"]},
        live=True,
    ),
    Param(
        "exit.take_profit", "Take profit", "float", None, "exit",
        help="Percent from entry. Empty means no take-profit.",
        min=0, step=0.0001, unit="%", percent=True,
        in_default=False, live=True,
    ),
    Param(
        "exit.tp_close", "Take profit on close", "bool", False, "exit",
        help="Wait for a close through the target instead of filling intrabar.",
        live=True,
    ),
    Param(
        "exit.trailing.k", "Trailing distance", "float", 3.0, "exit",
        help="NATR multiple for the trailing stop. Set a value to enable "
             "trailing; delete it to disable.",
        min=0, step=0.1, in_default=False,
        visible_if={"path": "exit.trailing", "exists": True},
        live=True,
    ),
    Param(
        "exit.trailing.natr", "Trailing ATR window", "int", 24, "exit",
        help="Bars in the NATR used by the trailing stop.",
        min=1, step=1, unit="bar", in_default=False,
        visible_if={"path": "exit.trailing", "exists": True},
        live=True,
    ),
    Param(
        "exit.limit", "Resting limit", "float", None, "exit",
        help="Legacy capitulation limit offset, in percent.",
        step=0.0001, unit="%", percent=True, in_default=False,
        status="unsupported", backtest=False, live=False,
        reason="Only the legacy capitulation path places resting limits; "
               "the spec backtester ignores them.",
    ),
    Param(
        "exit.exit_conditions", "Exit conditions", "condition", None, "exit",
        help="A condition tree that closes the position on the bar it first "
             "fires, after the stop and take-profit have had their say.",
        in_default=False, backtest=True, live=True,
    ),
    Param(
        "sizing.risk", "Risk per trade", "float", 0.0075, "sizing",
        help="Percent of equity risked to the stop.",
        min=0, step=0.0001, unit="%", percent=True, live=True,
    ),
    Param(
        "sizing.notional_cap", "Notional cap", "float", 0.20, "sizing",
        help="Maximum notional as a percent of equity.",
        min=0, step=0.0001, unit="%", percent=True, live=True,
    ),
    Param(
        "sizing.weight", "Portfolio weight", "float", 1.0, "sizing",
        help="Stored allocation hint; the single-bot engine does not read it.",
        min=0, step=0.1, in_default=False, live=True,
        status="ignored",
        reason="The single-bot backtest and runtime have no portfolio "
               "allocation step; this value is stored but has no effect.",
    ),
)

PARAM_BY_KEY = {p.key: p for p in PARAMS}


def _feature(id: str, label: str, path: str, *, op: str = "eq",
             value: Any = None, values: tuple = (), backtest: bool = True,
             live: bool = False, status: str = "ok",
             reason: str = "") -> dict:
    out = {"id": id, "label": label, "path": path, "op": op,
           "backtest": backtest, "live": live, "status": status,
           "reason": reason}
    if value is not None:
        out["value"] = value
    if values:
        out["values"] = list(values)
    return out


FEATURES = (
    _feature("side.short", "Short book", "side", value="short", live=True),
    _feature("side.long", "Long book", "side", value="long", live=True),
    _feature("side.both", "Two-sided book", "side", value="both",
             backtest=True, live=True),
    _feature("stop.none", "No stop", "exit.stop.mode", value="none", live=True),
    _feature("stop.hh", "Signal-window extreme stop", "exit.stop.mode",
             value="hh", live=True),
    _feature("stop.dstop", "Disaster stop", "exit.stop.mode",
             value="dstop", live=True),
    _feature("stop.sig", "Signal-window midpoint stop", "exit.stop.mode",
             value="sig", live=True),
    _feature(
        "stop.trail", "Legacy trailing mode", "exit.stop.mode", value="trail",
        backtest=False, live=False, status="unsupported",
        reason="stop.mode='trail' is a no-op; use exit.trailing.",
    ),
    _feature(
        "exit.trailing", "Trailing exit", "exit.trailing", op="exists",
        backtest=True, live=True,
    ),
    _feature(
        "exit.limit", "Resting limit", "exit.limit", op="exists",
        backtest=False, live=False, status="unsupported",
        reason="Only the legacy capitulation path places resting limits.",
    ),
    _feature(
        "exit.exit_conditions", "Exit conditions", "exit.exit_conditions",
        op="exists", backtest=True, live=True,
    ),
    _feature("exit.tp_close", "Take profit on close", "exit.tp_close",
             value=True, live=True),
    _feature(
        "operand.cross_series", "Multi-timeframe / cross-asset operand",
        "entry", op="cross_series", backtest=True, live=True,
    ),
    _feature(
        "filters", "Live regime filters", "filters", op="nonempty",
        backtest=True, live=True, status="partial",
        reason="BTC-bear, regime-veto and ticker filters are applied live; "
               "the backtest is unfiltered, so read those results as the "
               "strategy before filters.",
    ),
    _feature(
        "sizing.weight", "Portfolio weight", "sizing.weight", op="neq",
        value=1.0, backtest=True, live=True, status="ignored",
        reason="Weights are stored but the single-bot engine never reads "
               "them.",
    ),
)


def get_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def set_path(obj: dict, path: str, value: Any) -> dict:
    """Return a deep-copied object with `path` set (or removed when None)."""
    out = deepcopy(obj)
    parts = path.split(".")
    cur = out
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    if value is None:
        cur.pop(parts[-1], None)
    else:
        cur[parts[-1]] = deepcopy(value)
    return out


def default_spec() -> dict:
    spec: dict = {}
    for p in PARAMS:
        if p.in_default:
            spec = set_path(spec, p.key, p.default)
    return spec


def _clean_exit(ex: dict) -> dict:
    """Drop empty optional objects so they cannot masquerade as features."""
    if ex.get("trailing") in (None, {}, False):
        ex.pop("trailing", None)
    if ex.get("limit") is None:
        ex.pop("limit", None)
    if not ex.get("exit_conditions"):
        ex.pop("exit_conditions", None)
    if ex.get("take_profit") is None:
        ex.pop("take_profit", None)
    return ex


def normalize_spec(spec: dict) -> dict:
    """Drop empty optional objects so they cannot masquerade as features. A
    two-sided bot carries exit_long/exit_short instead of one exit; clean each."""
    out = deepcopy(spec)
    for key in ("exit", "exit_long", "exit_short"):
        if isinstance(out.get(key), dict):
            _clean_exit(out[key])
    return out


def timing_sets(spec: dict) -> tuple[frozenset, frozenset]:
    timing = spec.get("timing") or {}
    hours = timing.get("hours_utc") or ()
    days = timing.get("days_utc") or ()
    return frozenset(hours), frozenset(days)


def _uses_cross_series(spec: dict) -> bool:
    """True if any operand in the spec's condition trees reads another
    timeframe/instrument (carries tf or symbol)."""
    def op_cross(o):
        if not isinstance(o, dict):
            return False
        if "ind" in o:
            return o.get("tf") is not None or o.get("symbol") is not None
        if "op" in o:
            return op_cross(o.get("left")) or op_cross(o.get("right"))
        return False

    def node_cross(n):
        if not isinstance(n, dict):
            return False
        if "children" in n:
            return any(node_cross(c) for c in n["children"])
        return op_cross(n.get("left")) or op_cross(n.get("right"))

    trees = [spec[k] for k in ("entry", "entry_long", "entry_short")
             if spec.get(k)]
    for xk in ("exit", "exit_long", "exit_short"):
        ex = spec.get(xk)
        if isinstance(ex, dict) and ex.get("exit_conditions"):
            trees.append(ex["exit_conditions"])
    return any(node_cross(t) for t in trees)


def _feature_active(f: dict, spec: dict) -> bool:
    op = f.get("op", "eq")
    if op == "cross_series":
        return _uses_cross_series(spec)
    v = get_path(spec, f["path"])
    if op == "exists":
        return v is not None
    if op == "nonempty":
        return bool(v)
    if op == "neq":
        return v is not None and v != f.get("value")
    if op == "in":
        return v in (f.get("values") or ())
    return v == f.get("value")


def spec_issues(spec: dict, target: str = "backtest") -> list[dict]:
    """Features in this spec that the target engine cannot run (or runs only
    partially). `blocking` is the deploy/train gate; warnings are honest but
    do not stop the lab."""
    if target not in TARGETS:
        raise ValueError(f"target must be one of {TARGETS}")
    out = []
    for f in FEATURES:
        if not _feature_active(f, spec):
            continue
        supported = bool(f.get(target, True))
        status = f.get("status", "ok")
        if supported and status == "ok":
            continue
        out.append({
            "id": f["id"],
            "label": f["label"],
            "path": f["path"],
            "status": status,
            "backtest": bool(f.get("backtest", True)),
            "live": bool(f.get("live", False)),
            "blocking": not supported,
            "reason": f.get("reason", ""),
        })
    return out


def blocking_issues(spec: dict, target: str = "backtest") -> list[dict]:
    return [i for i in spec_issues(spec, target) if i["blocking"]]
