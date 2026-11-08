import { useEffect, useState } from "react";

/** Subscribe to a CSS media query from JS. Mirrors the CSS breakpoint spine
 *  (see theme.css) for the cases where layout has to branch in markup, not CSS
 *  — e.g. rendering a different component tree on phones vs desktop. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia(query).matches : false,
  );
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setMatches(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [query]);
  return matches;
}

/** The one true phone breakpoint (see theme.css: PHONE = max-width 860px). */
export function useIsPhone(): boolean {
  return useMediaQuery("(max-width: 860px)");
}
