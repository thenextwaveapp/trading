import type { ReactNode } from "react";
import s from "./Segmented.module.css";

export interface SegOption<T> {
  value: T;
  label: ReactNode;
  /** only used by labels="selected": the always-visible glyph */
  icon?: ReactNode;
  title?: string;
  disabled?: boolean;
}

/** The app's one segmented control — a thin glass pill with a selected thumb
 *  that slides between equal-width options. Replaces the copied .seg/.segBtn,
 *  .tab/.on, chart .rb and .ivb patterns. Works with text or icon labels.
 *
 *  size:   "sm" compact (chart/toolbar), "md" default (page filters)
 *  block:  stretch to the container width instead of hugging its content
 *  labels: "selected" shows icons only, expanding the active cell to reveal
 *          its text label. Cells are unequal width in this mode, so the
 *          sliding thumb is replaced by a pill on the active button itself.
 */
export default function Segmented<T extends string | number | boolean | null>({
  options,
  value,
  onChange,
  size = "md",
  block = false,
  labels = "always",
  ariaLabel,
}: {
  options: SegOption<T>[];
  value: T;
  onChange: (v: T) => void;
  size?: "sm" | "md";
  block?: boolean;
  labels?: "always" | "selected";
  ariaLabel?: string;
}) {
  const idx = options.findIndex((o) => o.value === value);
  const collapse = labels === "selected";
  const cls = [s.seg, size === "sm" ? s.sm : "", block ? s.block : "", collapse ? s.collapse : ""]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={cls}
      role="tablist"
      aria-label={ariaLabel}
      style={{ "--n": options.length } as React.CSSProperties}
    >
      {idx >= 0 && (
        <span className={s.thumb} aria-hidden style={{ "--i": idx } as React.CSSProperties} />
      )}
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          role="tab"
          aria-selected={o.value === value}
          className={`${s.btn} ${o.value === value ? s.on : ""}`}
          title={o.title ?? (collapse && typeof o.label === "string" ? o.label : undefined)}
          disabled={o.disabled}
          onClick={() => onChange(o.value)}
        >
          {collapse ? (
            <>
              {o.icon}
              <span className={s.lbl}>{o.label}</span>
            </>
          ) : (
            o.label
          )}
        </button>
      ))}
    </div>
  );
}
