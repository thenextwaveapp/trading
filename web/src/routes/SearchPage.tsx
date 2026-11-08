import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { SearchResults, useSearchResults } from "../components/SearchPalette";
import s from "./SearchPage.module.css";

/** Full-page search — the mobile counterpart to the desktop ⌘K overlay. Reached
 *  from the bottom-nav Search tab, so it has real back-button behaviour instead
 *  of floating over whatever page you were on. */
export default function SearchPage() {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const { groups, flat } = useSearchResults(q);

  // Don't auto-focus on landing — on phones that pops the keyboard (and an iOS
  // zoom) the instant you open the tab. Let the user tap the field when ready.
  useEffect(() => setActive(0), [q]);

  return (
    <div className={s.page}>
      <div className={s.head}>
        <button className={s.back} onClick={() => nav(-1)} aria-label="Back">
          <ArrowLeft size={20} strokeWidth={1.75} />
        </button>
        <div className={s.field}>
          <Search size={17} strokeWidth={1.5} style={{ color: "var(--muted)", flex: "none" }} />
          <input
            ref={inputRef}
            className={s.input}
            placeholder="Search bots, challenges, builders, instruments…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>
      <div className={s.results}>
        <SearchResults
          groups={groups}
          flat={flat}
          query={q}
          active={active}
          setActive={setActive}
          onPick={(r) => nav(r.path)}
        />
      </div>
    </div>
  );
}
