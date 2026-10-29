import s from "./Skeleton.module.css";

export function Skeleton({ w = "100%", h = 13, r, style }: {
  w?: number | string; h?: number | string; r?: string; style?: React.CSSProperties;
}) {
  return <div className={s.sk} style={{ width: w, height: h, borderRadius: r, ...style }} />;
}

/** A card of shimmer rows — stands in for a table or list while it loads, so the
 *  layout holds its space and nothing jumps when the real rows arrive. */
export function RowsSkeleton({ rows = 12, avatar = false }: { rows?: number; avatar?: boolean }) {
  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className={s.rowline}>
          {avatar && <Skeleton w={28} h={28} r="50%" />}
          <Skeleton w={`${34 + ((i * 11) % 38)}%`} h={13} />
          <Skeleton w={54} h={13} style={{ marginLeft: "auto" }} />
        </div>
      ))}
    </div>
  );
}

export function CardsSkeleton({ cards = 6 }: { cards?: number }) {
  return (
    <div className={s.cards}>
      {Array.from({ length: cards }).map((_, i) => (
        <div key={i} className={`card ${s.cardSk}`}>
          <Skeleton w="55%" h={18} />
          <Skeleton w="90%" h={13} />
          <Skeleton w="40%" h={13} />
        </div>
      ))}
    </div>
  );
}
