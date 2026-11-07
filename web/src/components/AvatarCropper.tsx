import { useEffect, useRef, useState } from "react";
import p from "../routes/pages.module.css";
import s from "./AvatarCropper.module.css";

const V = 260; // viewport diameter (px)
const OUT = 512; // exported square size (px)

// Standard avatar crop: load the picked image, let the user pan (drag) and zoom
// within a circular viewport, then export the visible circle as a square PNG
// File. No dependency — just a canvas. onSave receives the cropped File.
export default function AvatarCropper({
  file,
  onCancel,
  onSave,
  busy,
}: {
  file: File;
  onCancel: () => void;
  onSave: (cropped: File) => void;
  busy?: boolean;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [nat, setNat] = useState<{ w: number; h: number } | null>(null);
  const [zoom, setZoom] = useState(1);
  const [off, setOff] = useState({ x: 0, y: 0 });
  const imgRef = useRef<HTMLImageElement | null>(null);
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);

  useEffect(() => {
    const u = URL.createObjectURL(file);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  // cover scale: smallest scale that still fills the circle, then × zoom.
  const cover = nat ? Math.max(V / nat.w, V / nat.h) : 1;
  const sc = cover * zoom;
  const dispW = nat ? nat.w * sc : V;
  const dispH = nat ? nat.h * sc : V;

  const clamp = (x: number, y: number) => {
    const mx = Math.max(0, (dispW - V) / 2);
    const my = Math.max(0, (dispH - V) / 2);
    return { x: Math.min(mx, Math.max(-mx, x)), y: Math.min(my, Math.max(-my, y)) };
  };

  // re-clamp whenever zoom changes so the image never pulls off the circle.
  useEffect(() => {
    setOff((o) => clamp(o.x, o.y));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoom, nat]);

  const onDown = (e: React.PointerEvent) => {
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, y: e.clientY, ox: off.x, oy: off.y };
  };
  const onMove = (e: React.PointerEvent) => {
    if (!drag.current) return;
    const dx = e.clientX - drag.current.x;
    const dy = e.clientY - drag.current.y;
    setOff(clamp(drag.current.ox + dx, drag.current.oy + dy));
  };
  const onUp = () => {
    drag.current = null;
  };

  const save = () => {
    const img = imgRef.current;
    if (!img || !nat) return;
    // viewport (0..V) maps back to source pixels through the display scale.
    const srcSize = V / sc;
    const left = V / 2 + off.x - dispW / 2;
    const top = V / 2 + off.y - dispH / 2;
    const sx = -left / sc;
    const sy = -top / sc;
    const canvas = document.createElement("canvas");
    canvas.width = OUT;
    canvas.height = OUT;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(img, sx, sy, srcSize, srcSize, 0, 0, OUT, OUT);
    canvas.toBlob(
      (blob) => blob && onSave(new File([blob], "avatar.png", { type: "image/png" })),
      "image/png",
    );
  };

  return (
    <div className={s.overlay} onClick={(e) => e.target === e.currentTarget && onCancel()}>
      <div className={s.panel} role="dialog" aria-modal="true" aria-label="Crop photo">
        <div className={s.title}>Position and size your photo</div>

        <div className={s.stage} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}>
          {url && (
            <img
              ref={imgRef}
              src={url}
              alt=""
              draggable={false}
              className={s.img}
              onLoad={(e) => setNat({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
              style={{ width: dispW, height: dispH, left: V / 2 + off.x - dispW / 2, top: V / 2 + off.y - dispH / 2 }}
            />
          )}
        </div>

        <label className={s.zoom}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <circle cx="11" cy="11" r="7" /><path d="m20 20-3-3M8 11h6M11 8v6" />
          </svg>
          <input type="range" min={1} max={3} step={0.01} value={zoom} onChange={(e) => setZoom(Number(e.target.value))} aria-label="Zoom" />
        </label>

        <div className={s.actions}>
          <button className={`${p.btn} ${p.sm}`} onClick={onCancel} disabled={busy}>Cancel</button>
          <button className={`${p.btn} ${p.sm} ${p.pri}`} onClick={save} disabled={busy || !nat}>
            {busy ? "Saving…" : "Save photo"}
          </button>
        </div>
      </div>
    </div>
  );
}
