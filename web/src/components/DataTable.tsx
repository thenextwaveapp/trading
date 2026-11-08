import { useState, type ReactNode } from "react";
import s from "./DataTable.module.css";

export interface Column<T> {
  key: string;
  label: ReactNode;
  align?: "left" | "right";
  sortable?: boolean;
  /** sort value; omit for non-sortable columns */
  value?: (row: T) => string | number | null | undefined;
  render: (row: T, index: number) => ReactNode;
  /** Drop this column on phones — the table stays a table, just narrower. Use
   *  on the low-value columns so the best few fields fit without scrolling. */
  hidePhone?: boolean;
}

interface Sort {
  col: string | null;
  dir: 1 | -1;
}

const PER_PAGE = [10, 25, 50, 100];

export default function DataTable<T>({
  columns,
  rows,
  initialSort,
  pageSize = 10,
  onRowClick,
  rowClass,
  rowKey,
}: {
  columns: Column<T>[];
  rows: T[];
  initialSort?: { col: string; dir?: 1 | -1 };
  pageSize?: number;
  onRowClick?: (row: T) => void;
  rowClass?: (row: T) => string | undefined;
  rowKey?: (row: T) => string | number;
}) {
  const [sort, setSort] = useState<Sort>(
    initialSort ? { col: initialSort.col, dir: initialSort.dir ?? -1 } : { col: null, dir: -1 },
  );
  const [page, setPage] = useState(0);
  const [per, setPer] = useState(pageSize);

  let sorted = rows;
  if (sort.col) {
    const c = columns.find((x) => x.key === sort.col);
    if (c?.value) {
      sorted = rows.slice().sort((a, b) => {
        const x = c.value!(a),
          y = c.value!(b);
        if (x == null && y == null) return 0;
        if (x == null) return 1;
        if (y == null) return -1;
        if (typeof x === "string" && typeof y === "string")
          return x.localeCompare(y) * sort.dir;
        return ((x as number) - (y as number)) * sort.dir;
      });
    }
  }

  const nPages = Math.max(1, Math.ceil(sorted.length / per));
  const p = Math.min(page, nPages - 1);
  const pageRows = sorted.slice(p * per, (p + 1) * per);

  const onSort = (c: Column<T>) => {
    if (!c.sortable) return;
    setPage(0);
    setSort((cur) => {
      if (cur.col === c.key) return { col: c.key, dir: (cur.dir * -1) as 1 | -1 };
      // Default direction from first row: strings asc, numbers desc.
      const sample = c.value?.(rows[0]);
      return { col: c.key, dir: typeof sample === "string" ? 1 : -1 };
    });
  };

  const arrow = (key: string) =>
    sort.col === key ? (sort.dir > 0 ? " ▲" : " ▼") : "";

  return (
    <>
      <div className={s.wrap}>
        <table className={s.table}>
          <thead>
            <tr>
              {columns.map((c) => (
                <th
                  key={c.key}
                  className={`${s.th} ${c.align === "left" ? s.left : ""} ${c.sortable ? s.sortable : ""} ${c.hidePhone ? s.hidePhone : ""}`}
                  onClick={() => onSort(c)}
                >
                  {c.label}
                  {c.sortable ? arrow(c.key) : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.length === 0 ? (
              <tr>
                <td className={s.empty} colSpan={columns.length}>
                  none
                </td>
              </tr>
            ) : (
              pageRows.map((row, i) => (
                <tr
                  key={rowKey ? rowKey(row) : i}
                  className={`${s.row} ${onRowClick ? s.clickable : ""} ${rowClass?.(row) ?? ""}`}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                >
                  {columns.map((c) => (
                    <td
                      key={c.key}
                      className={`${s.td} ${c.align === "left" ? s.left : ""} ${c.hidePhone ? s.hidePhone : ""}`}
                    >
                      {c.render(row, p * per + i)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {sorted.length > 10 && (
        <div className={s.pager}>
          <span>{sorted.length} rows</span>
          <span className={s.spacer} />
          <button className={s.pbtn} disabled={p === 0} onClick={() => setPage(p - 1)} aria-label="previous page">
            ‹
          </button>
          <span>
            Page {p + 1} of {nPages}
          </span>
          <button className={s.pbtn} disabled={p >= nPages - 1} onClick={() => setPage(p + 1)} aria-label="next page">
            ›
          </button>
          <select
            className={s.perpg}
            value={per}
            onChange={(e) => {
              setPer(Number(e.target.value));
              setPage(0);
            }}
            aria-label="rows per page"
          >
            {PER_PAGE.map((n) => (
              <option key={n} value={n}>
                {n} / page
              </option>
            ))}
          </select>
        </div>
      )}
    </>
  );
}
