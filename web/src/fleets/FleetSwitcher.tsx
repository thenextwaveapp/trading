import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { createFleet } from "../db/queries";
import type { DbFleet } from "../db/types";
import { entitlementOf, FREE_MAX_FLEETS } from "../lib/billing";
import { useUpgrade } from "../components/UpgradeModal";
import { useCurrentFleet } from "./CurrentFleetProvider";
import s from "./FleetSwitcher.module.css";

/** The fleet picker on the fleet page: switch fleets, spin up a new one, or jump
 *  to the full settings. Closes on outside-click / Escape like a native menu.
 *  `variant="title"` renders the trigger as the section heading itself (the
 *  fleet's name), `"pill"` as a compact chip. */
export default function FleetSwitcher({ variant = "pill" }: { variant?: "pill" | "title" }) {
  const { fleets, current, setCurrentId, upsertFleet } = useCurrentFleet();
  const { user, subscription } = useAuth();
  const upgrade = useUpgrade();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!fleets.length) return null; // not loaded, or signed out

  const addFleet = async () => {
    if (!user || creating) return;
    if (!entitlementOf(subscription).entitled && fleets.length >= FREE_MAX_FLEETS) {
      setOpen(false);
      upgrade.open("Multiple fleets are a Pro feature.");
      return;
    }
    setCreating(true);
    const { data } = await createFleet(user.id, `Fleet ${fleets.length + 1}`);
    setCreating(false);
    if (!data) return;
    upsertFleet(data as DbFleet);
    setCurrentId((data as DbFleet).id);
    setOpen(false);
    // Land on the Fleets settings so the fresh fleet can be named + tuned.
    nav("/settings", { state: { tab: "Fleets" } });
  };

  return (
    <div className={s.wrap} ref={ref}>
      <button
        className={`${s.trigger} ${variant === "title" ? s.triggerTitle : ""}`}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span className={s.dot} style={{ background: current?.color ?? "#3a81d7" }} />
        <span className={s.name}>{current?.name ?? "Fleet"}</span>
        <svg className={s.caret} width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
          <path d="M4 6l4 4 4-4" />
        </svg>
      </button>

      {open && (
        <div className={s.menu} role="menu">
          <div className={s.menuLabel}>Your fleets</div>
          {fleets.map((f) => (
            <button
              key={f.id}
              className={`${s.item} ${current?.id === f.id ? s.itemSel : ""}`}
              role="menuitem"
              onClick={() => {
                setCurrentId(f.id);
                setOpen(false);
              }}
            >
              <span className={s.dot} style={{ background: f.color }} />
              <span className={s.itemName}>{f.name}</span>
              {current?.id === f.id && <span className={s.check}>✓</span>}
            </button>
          ))}
          <div className={s.sep} />
          <button className={s.action} onClick={addFleet} disabled={creating}>
            {creating ? "Creating…" : "＋ New fleet"}
          </button>
          <button
            className={s.action}
            onClick={() => {
              setOpen(false);
              nav("/settings", { state: { tab: "Fleets" } });
            }}
          >
            Fleet settings
          </button>
        </div>
      )}
    </div>
  );
}
