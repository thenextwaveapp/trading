"""Filesystem paths + logging for the live paper fleet. Leaf module — no sibling
imports, so every other fleet module can depend on it freely."""
import os
from datetime import datetime, timezone

DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "paper", "fleet")
LOG = os.path.join(DIR, "fleet.log")
PAUSE = os.path.join(DIR, "PAUSED")       # touch = no new entries (exits run)


def log(msg):
    line = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def iso(t):
    return datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%m-%d %H:%M")
