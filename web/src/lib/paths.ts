/** Readable URLs. Canonical detail paths hang off the builder's handle:
 *    /@handle                      builder profile
 *    /@handle/bot-slug             bot profile
 *    /@handle/bot-slug/TICKER/:t?  a single trade
 *  Bot names carry spaces; the slug column (or a client slugify of the name)
 *  keeps %20 out of the address bar. Legacy /bot/:name et al still resolve. */

export const slugify = (s: string): string =>
  s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "bot";

type BotLike = {
  name: string;
  slug?: string | null;
  builder?: { handle: string } | null;
};

export const botSlugOf = (b: BotLike): string => b.slug || slugify(b.name);

export const builderPath = (handle: string): string => "/@" + handle;

export const botPath = (b: BotLike): string =>
  b.builder?.handle
    ? `/@${b.builder.handle}/${botSlugOf(b)}`
    : "/bot/" + encodeURIComponent(b.name);

export const tradePath = (b: BotLike, ticker: string, t?: number | string | null): string =>
  b.builder?.handle
    ? `/@${b.builder.handle}/${botSlugOf(b)}/${ticker}${t ? "/" + t : ""}`
    : `/trade/${encodeURIComponent(b.name)}/${ticker}${t ? "/" + t : ""}`;
