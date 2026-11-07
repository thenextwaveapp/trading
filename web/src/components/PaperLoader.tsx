import s from "./PaperLoader.module.css";

/** The loading ritual: one sheet of paper, three lives. Plane → crumple →
 *  origami crane → crumple → folded bill → crumple → again.
 *
 *  Each shape is a bold silhouette split by a single fold into a lit face
 *  (paper white) and a shadowed/under face (fold blue or soft grey) — the same
 *  language as the brand plane. No scattered facets, no clipart crease strokes. */
const PAPER = "#E9ECF1"; // lit face
const FOLD = "#5E8FD8"; // brand-blue fold / underside
const SHADE = "#C3CBD6"; // soft shadowed face

export default function PaperLoader({ size = 64 }: { size?: number }) {
  return (
    <span className={s.box} style={{ width: size, height: size }} role="img" aria-label="Loading">
      {/* the paper plane — the brand mark */}
      <svg className={`${s.shape} ${s.s0}`} viewBox="0 0 64 64" fill="none" aria-hidden>
        <path d="M54.4 9.6 L9.6 30.4 L30.4 40 L54.4 9.6 Z" fill={PAPER} />
        <path d="M54.4 9.6 L34.2 41.9 L39 54.4 L43.8 43.8 L54.4 9.6 Z" fill={FOLD} />
      </svg>

      {/* the origami crane: wings up (one folded crease), neck + tail splayed */}
      <svg className={`${s.shape} ${s.s1}`} viewBox="0 0 64 64" fill="none" aria-hidden>
        {/* neck + beak, up-left (under face) */}
        <path d="M27 36 L11 13 L18 14 Z" fill={FOLD} />
        {/* tail, up-right (under face) */}
        <path d="M41 36 L56 18 L50 28 Z" fill={FOLD} />
        {/* breast, hanging (lit) */}
        <path d="M28 34 L44 34 L34 53 Z" fill={PAPER} />
        {/* wing, one solid fold */}
        <path d="M33 5 L20 34 L46 34 Z" fill={PAPER} />
      </svg>

      {/* the folded bill (the version you preferred): seal + denomination lines */}
      <svg className={`${s.shape} ${s.s2}`} viewBox="0 0 64 64" fill="none" aria-hidden>
        <path d="M6 21 L32 25 L58 21 L58 41 L32 45 L6 41 Z" fill="#E9ECF1" />
        <path d="M32 25 L32 45" stroke="#9AA4B2" strokeWidth="1.4" />
        <circle cx="19.5" cy="33" r="6.2" fill="#5E8FD8" />
        <path d="M41 30.5 H52 M41 36.5 H52" stroke="#9AA4B2" strokeWidth="1.6" strokeLinecap="round" />
      </svg>

      {/* the crumpled ball every life passes through: a soft blob, two big
          shadowed facets — folded paper collapsing, not shattered glass */}
      <svg className={`${s.ball}`} viewBox="0 0 64 64" fill="none" aria-hidden>
        <path d="M32 11 L42 13 L51 20 L54 31 L51 43 L42 51 L31 53 L21 50 L13 43 L10 31 L13 19 L22 13 Z" fill={PAPER} />
        <path d="M32 11 L54 31 L32 33 Z" fill={SHADE} />
        <path d="M31 53 L13 43 L32 33 Z" fill={SHADE} />
        {/* a couple of harsh creases — crumpled tension, not smooth */}
        <path
          d="M32 11 L32 33 M32 33 L42 51"
          stroke="#9AA4B2" strokeWidth="1.3" strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}
