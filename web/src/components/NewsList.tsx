import type { DbNews } from "../db/types";
import s from "./NewsList.module.css";

function rel(iso: string | null): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function NewsList({ rows, empty = "No headlines." }: { rows: DbNews[]; empty?: string }) {
  if (!rows.length) return <div className={`card ${s.empty}`}>{empty}</div>;
  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <div className={s.list}>
        {rows.map((n) => (
          <a key={n.id} href={n.url} target="_blank" rel="noreferrer" className={s.row}>
            <span className={s.title}>{n.title}</span>
            <span className={s.meta}>{n.source} · {rel(n.published_at)}</span>
          </a>
        ))}
      </div>
    </div>
  );
}
