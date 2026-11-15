import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "../ui";
import { ErrorState } from "./State";

/**
 * Reusable table with sortable headers, loading skeleton, error + empty states and pagination.
 * Sorting/filtering is done by the API; this component only displays the rows it is given.
 *
 * columns: [{ key, header, sortable?, render?(row), align? }]
 */
export default function DataTable({ columns, rows, rowKey = "id", loading, error, onRetry, sort, order, onSort, empty, pageSize = 8, caption }) {
  const [page, setPage] = useState(1);
  const pages = Math.max(1, Math.ceil((rows?.length ?? 0) / pageSize));
  useEffect(() => { if (page > pages) setPage(pages); }, [page, pages]);
  useEffect(() => { setPage(1); }, [sort, order]);

  if (error && !rows) return <ErrorState error={error} onRetry={onRetry} />;
  if (loading && !rows) {
    return (
      <div className="card-body" role="status" aria-label="Loading">
        {Array.from({ length: 5 }, (_, i) => <div key={i} className="skeleton" style={{ margin: "18px 0", width: `${90 - i * 7}%` }} />)}
      </div>
    );
  }
  if (!rows.length) return empty;

  const visible = rows.slice((page - 1) * pageSize, page * pageSize);
  const from = (page - 1) * pageSize + 1;

  return (
    <>
      {error && <ErrorState error={error} onRetry={onRetry} />}
      <div className={`table-wrap ${loading ? "refreshing" : ""}`} tabIndex={0} role="region" aria-label={caption}>
        <table className="table">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>
              {columns.map((c) => {
                const active = sort === c.key;
                const Icon = !active ? ArrowUpDown : order === "asc" ? ArrowUp : ArrowDown;
                return (
                  <th key={c.key} scope="col" style={{ textAlign: c.align }} aria-sort={active ? (order === "asc" ? "ascending" : "descending") : undefined}>
                    {c.sortable ? (
                      <button type="button" className="th-sort" onClick={() => onSort(c.key)}>
                        {c.header}
                        <Icon size={13} aria-hidden="true" />
                      </button>
                    ) : (
                      c.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => (
              <tr key={row[rowKey]}>
                {columns.map((c) => (
                  <td key={c.key} style={{ textAlign: c.align }}>{c.render ? c.render(row) : row[c.key]}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <nav className="pager" aria-label="Pagination">
          <span aria-live="polite">Showing {from}–{Math.min(page * pageSize, rows.length)} of {rows.length}</span>
          <div className="pager-btns">
            <Button size="sm" icon={ChevronLeft} onClick={() => setPage(page - 1)} disabled={page === 1} aria-label="Previous page">Prev</Button>
            <span>Page {page} of {pages}</span>
            <Button size="sm" onClick={() => setPage(page + 1)} disabled={page === pages} aria-label="Next page">Next<ChevronRight size={16} aria-hidden="true" /></Button>
          </div>
        </nav>
      )}
    </>
  );
}
