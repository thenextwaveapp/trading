"""Tiny stdlib .env loader. Reads KEY=VALUE lines from the repo-root .env
(and live/keys.env) into os.environ without overwriting existing values."""
import os


def _load(path):
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                # strip trailing inline comments
                if " #" in v:
                    v = v.split(" #", 1)[0].rstrip()
                if (v.startswith('"') and v.endswith('"')) or \
                   (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                os.environ.setdefault(k, v)
    except FileNotFoundError:
        pass


def load():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _load(os.path.join(root, ".env"))
    _load(os.path.join(root, "live", "keys.env"))
load()