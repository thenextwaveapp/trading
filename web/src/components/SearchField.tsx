import type { CSSProperties } from "react";
import { Search, X } from "lucide-react";
import s from "./SearchField.module.css";

// The shared page-filter search. One component so Market, Leaderboard (and any
// page with a filter row) look and behave identically — an elegant underline
// that lives ON the filter row, not a boxed input floating in the header.
export default function SearchField({
  value,
  onChange,
  placeholder = "Search",
  className,
  style,
  ariaLabel,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  style?: CSSProperties;
  ariaLabel?: string;
}) {
  return (
    <label className={className ? `${s.field} ${className}` : s.field} style={style}>
      <Search className={s.icon} size={15} strokeWidth={1.5} />
      <input
        className={s.input}
        type="text"
        placeholder={placeholder}
        aria-label={ariaLabel ?? placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {value && (
        <button type="button" className={s.clear} aria-label="Clear search" onClick={() => onChange("")}>
          <X size={13} strokeWidth={1.8} />
        </button>
      )}
    </label>
  );
}
