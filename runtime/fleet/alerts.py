"""ntfy phone alerts. ALERTS gates which categories fire; the topic + enable
flag live in <fleet>/ntfy.json."""
import json
import os
import threading
import urllib.request

from .base import DIR

NTFY_CFG = os.path.join(DIR, "ntfy.json")  # {"topic": "...", "enabled": true}

# Which alert categories fire. All on by default.
ALERTS = {"entries": True, "exits": True, "kill_switch": True,
          "errors": True, "fleet_updown": True, "pause": True}


def ntfy_topic():
    try:
        c = json.load(open(NTFY_CFG))
        return c.get("topic") if c.get("enabled", True) and c.get("topic") \
            else None
    except Exception:
        return None


def notify(title, msg, priority="default", tags=None, cat=None):
    """Push to the phone via ntfy.sh. Fire-and-forget; never blocks a cycle.
    cat maps to ALERTS[cat] (default on)."""
    if cat and not ALERTS.get(cat, True):
        return
    topic = ntfy_topic()
    if not topic:
        return

    def _send():
        try:
            hdrs = {"Title": title, "Priority": priority}
            if tags:
                hdrs["Tags"] = tags
            req = urllib.request.Request(f"https://ntfy.sh/{topic}",
                                         data=msg.encode(), headers=hdrs)
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()
