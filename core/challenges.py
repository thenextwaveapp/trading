"""Challenges — a full bot spec with one hole.

A Challenge is a template strategy plus a *lock-set*: the whole Setup is fixed
except for a small number of open `holes`. Entering a Challenge is a Copy of
the template that may differ from it only at those holes; the market then votes
and a `judge` ranks the field.

The rule, mirrored from `markets.available` and `params.spec_issues`: there is
one source of truth (the template), and the engine — not the UI — decides what
a legal entry is.

    an entry is legal iff
        every path where it differs from the template is covered by a hole
        AND every predicate on the Challenge holds

Three kinds of lock, all expressed the same way:
  - **open a value** — hole `exit.take_profit`; the leaf may change (pick TP%).
  - **open a subtree** — hole `entry`; rewrite the whole entry tree (shape
    Challenges constrain it with a predicate instead of a value lock).
  - **everything else locked** — any diff outside a hole rejects the entry,
    naming the offending path, so the lock is legible.

Judges score one entry's backtest/live result; relative judges (distance from
the median) score it against the whole field. `rank()` turns a set of results
into standings.
"""
from copy import deepcopy

from .indicators import REGISTRY
from .params import normalize_spec

EPS = 1e-9

# Identity/engine-internal keys never participate in lock enforcement: an entry
# always has its own name, parse() stamps `_`-prefixed fields, and the Weather
# gate (condition_filter) is a bot-row field governed by predicates, not the
# structural lock.
_IGNORE_KEYS = ("name", "condition_filter")


# --------------------------------------------------------------------------- #
# path access over specs (dicts AND the entry tree's lists)
# --------------------------------------------------------------------------- #

def _seg(part):
    """A path segment is a list index if it is all digits, else a dict key."""
    return int(part) if isinstance(part, int) or part.lstrip("-").isdigit() else part


def _split(path):
    return [_seg(p) for p in path.split(".")] if path else []


def get_at(obj, path):
    """Read `path` (dot notation, integer segments index lists). None if absent."""
    cur = obj
    for part in _split(path):
        if isinstance(part, int):
            if not isinstance(cur, list) or not (-len(cur) <= part < len(cur)):
                return None
            cur = cur[part]
        else:
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
    return cur


def set_at(obj, path, value):
    """Deep-copy `obj` with `path` set to `value`. Creates intermediate dicts
    for missing keys; list indices must already exist."""
    out = deepcopy(obj)
    parts = _split(path)
    cur = out
    for part in parts[:-1]:
        if isinstance(part, int):
            cur = cur[part]
        else:
            nxt = cur.get(part)
            if not isinstance(nxt, (dict, list)):
                nxt = {}
                cur[part] = nxt
            cur = nxt
    last = parts[-1]
    if isinstance(last, int):
        cur[last] = value
    else:
        cur[last] = value
    return out


# --------------------------------------------------------------------------- #
# the lock: diff a candidate against the template
# --------------------------------------------------------------------------- #

def _prune(node):
    """Drop identity/internal keys so they never read as a lock violation."""
    if isinstance(node, dict):
        return {k: _prune(v) for k, v in node.items()
                if k not in _IGNORE_KEYS and not str(k).startswith("_")}
    if isinstance(node, list):
        return [_prune(v) for v in node]
    return node


def _diff_paths(a, b, prefix=""):
    """Finest-grained paths where `a` and `b` differ. A key present on one side
    only, a changed list length, or a changed leaf each yield one path."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for key in a.keys() | b.keys():
            p = f"{prefix}.{key}" if prefix else str(key)
            if key not in a or key not in b:
                out.append(p)
            else:
                out.extend(_diff_paths(a[key], b[key], p))
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [prefix or "<root>"]
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out.extend(_diff_paths(x, y, f"{prefix}.{i}" if prefix else str(i)))
        return out
    return [] if a == b else [prefix or "<root>"]


def _covered(path, holes):
    """True if `path` is at or under some hole (the hole is an ancestor)."""
    segs = path.split(".")
    for h in holes:
        hs = h.split(".")
        if segs[:len(hs)] == hs:
            return True
    return False


def _canon(spec):
    """Canonical, comparable form of a spec. parse() applies every default
    (fresh, exit.time_bars, timing sorting, empty-optional pruning) so a
    candidate that merely spells out a default the template omitted does not
    read as a lock violation. Falls back to normalize_spec for partial specs."""
    from .strategy import parse, StrategyError  # local: avoid import cycles
    try:
        return _prune(parse(spec))
    except (StrategyError, KeyError, TypeError, ValueError):
        return _prune(normalize_spec(spec))


def check_locks(template, candidate, holes):
    """(ok, error). The entry is legal iff every path where it differs from the
    template is covered by a hole. The error names the first locked path the
    entry touched, so the lock is explainable."""
    t = _canon(template)
    c = _canon(candidate)
    for path in sorted(_diff_paths(t, c)):
        if not _covered(path, holes):
            return False, f"'{path}' is locked by this challenge"
    return True, None


# --------------------------------------------------------------------------- #
# predicates — the shape / restriction / constraint families
# --------------------------------------------------------------------------- #

def _walk_conditions(node):
    """Yield every leaf condition node in an entry tree."""
    if not isinstance(node, dict):
        return
    if "children" in node:
        for c in node["children"]:
            yield from _walk_conditions(c)
    else:
        yield node


def _indicators_used(entry):
    out = []
    for cond in _walk_conditions(entry):
        for side in ("left", "right"):
            o = cond.get(side)
            if isinstance(o, dict) and "ind" in o:
                out.append(o["ind"])
    return out


def _node_count(node):
    if not isinstance(node, dict):
        return 0
    if "children" in node:
        return 1 + sum(_node_count(c) for c in node["children"])
    return 1


def _pred_range(spec, cfg):
    v = get_at(spec, cfg["path"])
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return False, f"{cfg['path']} must be a number"
    lo, hi = cfg.get("min"), cfg.get("max")
    if lo is not None and v < lo:
        return False, f"{cfg['path']} must be >= {lo}"
    if hi is not None and v > hi:
        return False, f"{cfg['path']} must be <= {hi}"
    return True, None


def _pred_max_nodes(spec, cfg):
    n = _node_count(get_at(spec, cfg.get("path", "entry")))
    k = cfg["max"]
    return (n <= k, None if n <= k else f"entry has {n} nodes, max is {k}")


def _pred_distinct_indicators(spec, cfg):
    used = set(_indicators_used(get_at(spec, cfg.get("path", "entry")) or {}))
    n = len(used)
    if "exact" in cfg and n != cfg["exact"]:
        return False, f"entry must reference exactly {cfg['exact']} indicator(s), has {n}"
    if "min" in cfg and n < cfg["min"]:
        return False, f"entry must reference >= {cfg['min']} indicator(s), has {n}"
    if "max" in cfg and n > cfg["max"]:
        return False, f"entry may reference <= {cfg['max']} indicator(s), has {n}"
    return True, None


def _pred_indicators_in(spec, cfg):
    allowed = set(cfg["allowed"])
    bad = sorted(set(_indicators_used(get_at(spec, cfg.get("path", "entry")) or {})) - allowed)
    if bad:
        return False, f"indicator(s) not allowed in this challenge: {', '.join(bad)}"
    return True, None


def _pred_indicators_not_in(spec, cfg):
    banned = set(cfg["banned"])
    bad = sorted(set(_indicators_used(get_at(spec, cfg.get("path", "entry")) or {})) & banned)
    if bad:
        return False, f"indicator(s) banned in this challenge: {', '.join(bad)}"
    return True, None


def _pred_no_weather(spec, _cfg):
    cf = spec.get("condition_filter")
    return (not cf, None if not cf else "this challenge forbids a Weather gate")


# --- shape challenges: the entry AST must match a named pattern ------------ #
# Matched structurally and by indicator *category*, so the shapes survive the
# full TA-Lib registry (212 indicators) without hard-coding ids. A moving
# average is anything in "Overlap Studies"; a bare price is category "price".
MA_FAMILIES = ("overlap",)
_SINGLE_CANDLE_IDS = ("open", "high", "low", "close", "volume",
                      "WICK_FRAC", "VOL_RATIO", "CLOSE_POS")
_CAT_SUFFIXES = (" indicators", " studies", " functions", " transform")


def _is_ind(o):
    return isinstance(o, dict) and "ind" in o


def _category(o):
    ind = REGISTRY.get(o.get("ind")) if _is_ind(o) else None
    return ind.category if ind else ""


def _family(o):
    """Normalized indicator family. The registry mixes TA-Lib categories
    ('Momentum Indicators') with hand-rolled ones ('momentum'); fold both to a
    single token so 'different families' is reliable."""
    c = _category(o).lower().strip()
    for suf in _CAT_SUFFIXES:
        if c.endswith(suf):
            return c[:-len(suf)].strip()
    return c


def _top_conditions(entry):
    """Leaf comparisons directly under the entry's top group (one level)."""
    if isinstance(entry, dict) and "children" in entry:
        return [c for c in entry["children"] if "children" not in c]
    return [entry] if isinstance(entry, dict) and "op" in entry else []


def _shape_pure_cross(entry, cfg):
    conds = list(_walk_conditions(entry))
    if len(conds) != 1:
        return False, "Pure Cross: the entry must be a single cross condition"
    c = conds[0]
    if c.get("op") not in ("crosses_above", "crosses_below"):
        return False, "Pure Cross: the operator must be a cross"
    fams = tuple(cfg.get("families") or MA_FAMILIES)
    if not (_is_ind(c.get("left")) and _is_ind(c.get("right"))):
        return False, "Pure Cross: both sides must be moving averages"
    if not (_family(c["left"]) in fams and _family(c["right"]) in fams):
        return False, "Pure Cross: both sides must be moving averages"
    return True, None


def _shape_pure_breakout(entry, _cfg):
    conds = list(_walk_conditions(entry))
    if len(conds) != 1:
        return False, "Pure Breakout: a single condition only"
    c = conds[0]
    if c.get("op") not in ("gt", "ge", "lt", "le"):
        return False, "Pure Breakout: must be a > / < comparison"
    left, right = c.get("left"), c.get("right")
    price_side = _category(left) == "price" or _category(right) == "price"
    level_side = (_is_ind(left) and _category(left) != "price") or \
                 (_is_ind(right) and _category(right) != "price")
    if not (price_side and level_side):
        return False, "Pure Breakout: compare a price to a channel level (e.g. close vs a band)"
    return True, None


def _shape_two_factor(entry, _cfg):
    if not (isinstance(entry, dict) and entry.get("logic") == "AND"):
        return False, "Two-Factor: the entry must be an AND of two factors"
    conds = _top_conditions(entry)
    if len(conds) != 2 or any("children" in c for c in entry["children"]):
        return False, "Two-Factor: exactly two comparisons, no nesting"
    cats = []
    for c in conds:
        ind = c.get("left") if _is_ind(c.get("left")) else c.get("right")
        other = c.get("right") if ind is c.get("left") else c.get("left")
        if not _is_ind(ind) or _is_ind(other):
            return False, "Two-Factor: each factor is one indicator vs a constant"
        cats.append(_family(ind))
    if cats[0] == cats[1]:
        return False, "Two-Factor: the two factors must be different indicator families"
    return True, None


def _shape_single_candle(entry, cfg):
    allowed = set(cfg.get("allowed") or _SINGLE_CANDLE_IDS)
    for c in _walk_conditions(entry):
        for side in ("left", "right"):
            o = c.get(side)
            if _is_ind(o):
                if o["ind"] not in allowed:
                    return False, f"Single Candle: {o['ind']} is not a single-bar input"
                if o.get("offset", 0) != 0:
                    return False, "Single Candle: no lookback offsets"
    return True, None


_SHAPES = {
    "pure_cross": _shape_pure_cross,
    "pure_breakout": _shape_pure_breakout,
    "two_factor": _shape_two_factor,
    "single_candle": _shape_single_candle,
}


def _pred_shape_match(spec, cfg):
    shape = cfg.get("shape")
    fn = _SHAPES.get(shape)
    if fn is None:
        return False, f"unknown shape: {shape!r}"
    return fn(spec.get("entry") or {}, cfg)


PREDICATES = {
    "range": _pred_range,
    "max_nodes": _pred_max_nodes,
    "distinct_indicators": _pred_distinct_indicators,
    "indicators_in": _pred_indicators_in,
    "indicators_not_in": _pred_indicators_not_in,
    "no_weather": _pred_no_weather,
    "shape_match": _pred_shape_match,
}


def check_predicates(spec, predicates):
    """(ok, error) — run each predicate; stop at the first failure."""
    for p in predicates or ():
        kind = p.get("kind")
        fn = PREDICATES.get(kind)
        if fn is None:
            return False, f"unknown challenge predicate: {kind!r}"
        ok, msg = fn(spec, p)
        if not ok:
            return False, msg
    return True, None


# --------------------------------------------------------------------------- #
# entry: build + validate a Copy of the template
# --------------------------------------------------------------------------- #

def build_entry(template, edits, holes):
    """Apply each edit (path -> value) to a Copy of the template. An edit whose
    path is not covered by a hole is rejected before anything is changed."""
    for path in (edits or {}):
        if not _covered(path, holes):
            raise ValueError(f"'{path}' is locked by this challenge")
    candidate = deepcopy(template)
    for path, value in (edits or {}).items():
        candidate = set_at(candidate, path, value)
    return candidate


def validate_entry(template, candidate, holes, predicates=None):
    """(ok, error) — the full legality check for an entered bot: it differs from
    the template only at open holes, and every predicate holds."""
    ok, err = check_locks(template, candidate, holes)
    if not ok:
        return False, err
    return check_predicates(candidate, predicates)


# --------------------------------------------------------------------------- #
# judges
# --------------------------------------------------------------------------- #

def _stats(result):
    return result.get("stats", result) or {}


def _nets(result):
    return [t["net"] for t in (result.get("trades") or [])]


def _m_return(result):
    return float(_stats(result).get("total_net_pct", 0.0))


def _m_calmar(result):
    s = _stats(result)
    dd = abs(float(s.get("max_drawdown", 0.0)))
    return float(s.get("total_net_pct", 0.0)) / max(dd, EPS)


def _m_profit_factor(result):
    nets = _nets(result)
    wins = sum(x for x in nets if x > 0)
    loss = -sum(x for x in nets if x < 0)
    if loss <= EPS:
        return float("inf") if wins > 0 else 0.0
    return wins / loss


def _m_low_drawdown(result):
    # max_drawdown is a non-positive fraction; closer to 0 is better, which is
    # already "higher is better" (-0.1 > -0.3).
    return float(_stats(result).get("max_drawdown", 0.0))


def _m_fewest_trades(result):
    # fewer trades is better -> negate the count.
    return -float(_stats(result).get("n", 0))


# A judge: metric (higher = better), eligibility gate, and whether it needs the
# whole field (relative).
# A no-trade entry never *did* anything, so it cannot place — every judge gates
# on at least one trade (some gate harder: a floor, or still-positive).
def _traded(r, _c):
    return _stats(r).get("n", 0) > 0


JUDGES = {
    "return":          {"metric": _m_return, "eligible": _traded, "relative": False},
    "calmar":          {"metric": _m_calmar, "eligible": _traded, "relative": False},
    "profit_factor":   {"metric": _m_profit_factor, "eligible": _traded, "relative": False},
    "low_drawdown":    {"metric": _m_low_drawdown,
                        "eligible": lambda r, c: _stats(r).get("n", 0) >= max(1, c.get("trade_floor", 0)),
                        "relative": False},
    "fewest_trades_positive": {"metric": _m_fewest_trades,
                        "eligible": lambda r, c: _stats(r).get("n", 0) > 0
                                     and _stats(r).get("total_net_pct", 0.0) > 0,
                        "relative": False},
    "median_distance": {"metric": _m_return, "eligible": _traded, "relative": True},
}


def _median(xs):
    s = sorted(xs)
    n = len(s)
    if not n:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def rank(entries, judge, cfg=None):
    """Rank `entries` (each {id, result}) by `judge`. Ineligible entries keep a
    None score and sort last. Returns standings:
        [{id, score, eligible, place}]  (place 1 = winner; None if ineligible)
    """
    cfg = cfg or {}
    spec = JUDGES.get(judge)
    if spec is None:
        raise ValueError(f"unknown judge: {judge!r}")
    metric, elig, relative = spec["metric"], spec["eligible"], spec["relative"]

    scored = []
    for e in entries:
        res = e["result"]
        ok = True if elig is None else bool(elig(res, cfg))
        scored.append({"id": e["id"], "eligible": ok,
                       "raw": metric(res) if ok else None})

    if relative:
        med = _median([s["raw"] for s in scored if s["eligible"] and s["raw"] is not None])
        for s in scored:
            s["score"] = -abs(s["raw"] - med) if s["eligible"] and s["raw"] is not None else None
    else:
        for s in scored:
            s["score"] = s["raw"]
    for s in scored:
        s.pop("raw", None)

    eligible = [s for s in scored if s["eligible"] and s["score"] is not None]
    ineligible = [s for s in scored if not (s["eligible"] and s["score"] is not None)]
    eligible.sort(key=lambda s: s["score"], reverse=True)
    for i, s in enumerate(eligible):
        s["place"] = i + 1
    for s in ineligible:
        s["place"] = None
    return eligible + ineligible


def score_twin(result_long, result_short, judge, cfg=None):
    """Twin challenge: the same skeleton entered long and short, scored by the
    *worse* of the two books. One lucky direction cannot carry the entry."""
    cfg = cfg or {}
    spec = JUDGES.get(judge)
    if spec is None:
        raise ValueError(f"unknown judge: {judge!r}")
    return min(spec["metric"](result_long), spec["metric"](result_short))
