import { useEffect, type ReactNode } from "react";
import s from "./Drawer.module.css";

/** Right-side slide-in panel on the blurred modal overlay. Safe to exit: click
 *  the dimmed backdrop, press Esc, or the labelled Close button — never a lone
 *  tiny x. */
export default function Drawer({
  title,
  onClose,
  children,
  footer,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <>
      <div className="ovl" onClick={onClose} />
      <aside className={s.panel} role="dialog" aria-label={title}>
        <div className={s.head}>
          <span className={s.title}>{title}</span>
          <button className={s.close} onClick={onClose}>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" />
            </svg>
            Close
          </button>
        </div>
        <div className={s.body}>{children}</div>
        {footer && <div className={s.footer}>{footer}</div>}
      </aside>
    </>
  );
}
