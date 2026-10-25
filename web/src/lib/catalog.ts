import catalog from "../data/catalog.json";

export interface CatalogParam {
  name: string;
  type: string;
  default: unknown;
  min: number | null;
  max: number | null;
}

export interface CatalogIndicator {
  id: string;
  label: string;
  category: string;
  inputs: string[];
  params: CatalogParam[];
}

export interface CatalogMarket {
  id: string;
  label: string;
  provides: string[];
  series_kind: string;
  asset_class: string;
}

export interface Catalog {
  indicators: CatalogIndicator[];
  markets: CatalogMarket[];
  counts: { indicators: number; markets: number };
}

export const CATALOG = catalog as unknown as Catalog;

export function marketById(id: string): CatalogMarket | undefined {
  return CATALOG.markets.find((m) => m.id === id);
}

export function indicatorsForMarket(marketId: string): CatalogIndicator[] {
  const m = marketById(marketId);
  if (!m) return [];
  return CATALOG.indicators.filter((ind) =>
    ind.inputs.every((i) => m.provides.includes(i)),
  );
}

export function indicatorById(id: string): CatalogIndicator | undefined {
  return CATALOG.indicators.find((i) => i.id === id);
}
