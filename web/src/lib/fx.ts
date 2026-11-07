import type { MouseEvent } from "react";

/** Writes the cursor position into CSS vars so a card's border can light up
 *  under the pointer (radial mask on a border-only ::after) — same effect as
 *  the landing hero card. */
export function edgeGlow(e: MouseEvent<HTMLElement>) {
  const r = e.currentTarget.getBoundingClientRect();
  e.currentTarget.style.setProperty("--mx", `${e.clientX - r.left}px`);
  e.currentTarget.style.setProperty("--my", `${e.clientY - r.top}px`);
}
