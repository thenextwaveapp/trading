"""Export the indicator + market catalog to JSON for the web app.

Writes web/src/data/catalog.json — the real registry (indicators with their
inputs/params and the market model), so the Builder/Indicators/Markets pages
render from the actual engine, not a hand-kept copy. Market availability is
computed client-side from inputs ⊆ provides.

Re-run after changing indicators or markets:  python3 -m core.export_catalog
"""
import json
import os

from core.indicators import REGISTRY
from core.markets import MARKETS


def _param(p):
    name, typ, default, mn, mx = p
    return {"name": name, "type": getattr(typ, "__name__", str(typ)),
            "default": default, "min": mn, "max": mx}


def build():
    indicators = [{
        "id": ind.id,
        "label": ind.label or ind.id,
        "category": ind.category,
        "inputs": list(ind.inputs),
        "params": [_param(p) for p in ind.params],
    } for ind in sorted(REGISTRY.values(), key=lambda x: (x.category, x.id))]

    markets = [{
        "id": m.id,
        "label": m.label,
        "provides": sorted(m.provides),
        "series_kind": m.series_kind,
        "asset_class": m.asset_class,
    } for m in MARKETS.values()]

    return {
        "indicators": indicators,
        "markets": markets,
        "counts": {"indicators": len(indicators), "markets": len(markets)},
    }


def main():
    data = build()
    path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "web", "src", "data", "catalog.json"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"wrote {path}")
    print(f"  {data['counts']['indicators']} indicators, "
          f"{data['counts']['markets']} markets")


if __name__ == "__main__":
    main()
