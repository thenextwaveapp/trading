"""Per-bot paper-trading state — equity, positions, trade log. One JSON file
and one trades CSV per bot id, under the fleet dir."""
import csv
import json
import os

from .base import DIR
from ..trade_model import START_EQUITY


def spath(name):
    return os.path.join(DIR, f"{name}.json")


def tpath(name):
    return os.path.join(DIR, f"trades_{name}.csv")


def load_state(name):
    if os.path.exists(spath(name)):
        st = json.load(open(spath(name)))
        st.setdefault("orders", [])
        return st
    return dict(equity=START_EQUITY, kill_until=0, last_sig_t=0,
                positions=[], eq_hist=[], orders=[])


def save_state(name, st):
    tmp = f"{spath(name)}.tmp.{os.getpid()}"
    json.dump(st, open(tmp, "w"), indent=1)
    os.replace(tmp, spath(name))


def record_trade(name, row):
    new = not os.path.exists(tpath(name))
    with open(tpath(name), "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ticker", "t_sig", "entry", "stop", "exit_t", "kind",
                        "net", "pnl", "notional", "equity_after"])
        w.writerow(row)
