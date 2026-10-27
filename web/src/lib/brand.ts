export const FLEET_PALETTE = [
  { name: "Blue", shades: ["#97c1f7", "#65a1ec", "#3a81d7", "#2463ae", "#144782"] },
  { name: "Amber", shades: ["#f8cb98", "#e5a65a", "#cb8315", "#a66800", "#7f4e00"] },
  { name: "Violet", shades: ["#b59be5", "#9b73da", "#814ec6", "#62349c", "#441f72"] },
  { name: "Teal", shades: ["#a0e2e5", "#63c6cc", "#19a9b0", "#00888e", "#00686d"] },
  { name: "Magenta", shades: ["#e99cc1", "#d970a5", "#c04688", "#982e6a", "#701c4c"] },
  { name: "Olive", shades: ["#d4d69b", "#b5b760", "#979828", "#797a11", "#5c5c07"] },
  { name: "Indigo", shades: ["#8a9cd3", "#657bc7", "#455bb2", "#2e408b", "#1a2761"] },
  { name: "Orange", shades: ["#f7b198", "#e78765", "#cf6139", "#a74824", "#7e3216"] },
] as const;

export const DEFAULT_BOT_COLOR = "#3a81d7";

export const FLEET_SLOTS: string[] = FLEET_PALETTE.map((h) => h.shades[2]);
export const FLEET_COLORS: string[] = FLEET_PALETTE.flatMap((h) => [...h.shades]);

export function botColor(
  bot?: {
    params?: Record<string, unknown> | null;
    builder?: { avatar_color?: string | null } | null;
  } | null,
): string {
  const c = bot?.params?.color;
  if (typeof c === "string" && c.trim()) return c;
  const av = bot?.builder?.avatar_color;
  if (typeof av === "string" && av.trim()) return av;
  return DEFAULT_BOT_COLOR;
}
