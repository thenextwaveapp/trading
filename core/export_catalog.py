"""Export the indicator + market catalog to JSON for the web app.

Writes web/src/data/catalog.json (indicators with their inputs/params, the
market model, and the typed strategy-parameter registry) so the
Builder/Indicators/Markets pages render from the engine registry. Market
availability is computed client-side from inputs ⊆ provides.

Re-run after changing indicators, markets, or core/params.py:
    python3 -m core.export_catalog
"""
import json
import os

from core.indicators import REGISTRY
from core.markets import MARKETS
from core.params import FEATURES, GROUPS, PARAMS, default_spec


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

    spec_params = [p.json() for p in PARAMS]

    return {
        "indicators": indicators,
        "markets": markets,
        "spec_params": spec_params,
        "spec_features": list(FEATURES),
        "spec_groups": list(GROUPS),
        "spec_defaults": {"name": "", **default_spec(), "filters": []},
        "counts": {"indicators": len(indicators), "markets": len(markets),
                   "spec_params": len(spec_params)},
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
          f"{data['counts']['markets']} markets, "
          f"{data['counts']['spec_params']} spec params")


if __name__ == "__main__":
    main()
