import { useState } from "react";
import { Pencil, Plus, Trash2, Users } from "lucide-react";
import { api } from "../services/api";
import { useFetch } from "../hooks/useFetch";
import { useDebounce } from "../hooks/useDebounce";
import { useMeta } from "../lib/MetaContext";
import PageHeader from "../components/shared/PageHeader";
import FilterBar from "../components/shared/FilterBar";
import DataTable from "../components/shared/DataTable";
import ConfirmDialog from "../components/shared/ConfirmDialog";
import { EmptyState } from "../components/shared/State";
import { Button, IconButton } from "../components/ui";
import { useToast } from "../components/ui/Toast";
import CandidateFormDialog from "../features/candidates/CandidateFormDialog";
import CandidateDetailDialog from "../features/candidates/CandidateDetailDialog";
import ApplicationFormDialog from "../features/applications/ApplicationFormDialog";
import { SOURCE_LABELS, formatDate, initials } from "../lib/format";
import { useAuth } from "../auth/AuthContext";

export default function Candidates() {
  const { can } = useAuth();
  const meta = useMeta();
  const toast = useToast();
  const [f, setF] = useState({ search: "", source: "" });
  const [sort, setSort] = useState("created_at");
  const [order, setOrder] = useState("desc");
  const [dialog, setDialog] = useState(null); // { type: 'create'|'edit'|'view'|'delete'|'apply', candidate? }
  const [detailKey, setDetailKey] = useState(0);
  const search = useDebounce(f.search);

  const { data, error, loading, refetch } = useFetch(
    (s) => api.candidates.list({ search, source: f.source, sort, order }, s),
    [search, f.source, sort, order]
  );

  const onSort = (key) => {
    if (key === sort) setOrder(order === "asc" ? "desc" : "asc");
    else { setSort(key); setOrder("asc"); }
  };
  const close = () => setDialog(null);
  const filtersActive = f.search || f.source;

  async function remove(c) {
    try {
      await api.candidates.remove(c.id);
      toast.success(`${c.full_name} was deleted.`);
      refetch();
    } catch (e) {
      toast.error(e.message);
    }
    close();
  }

  const columns = [
    { key: "full_name", header: "Candidate", sortable: true, render: (c) => (
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <span className="avatar" aria-hidden="true">{initials(c.full_name)}</span>
        <div><button type="button" className="link-btn" onClick={() => setDialog({ type: "view", candidate: c })}>{c.full_name}</button><div className="cell-sub">{c.id}</div></div>
      </div>
    ) },
    { key: "email", header: "Email", sortable: true },
    { key: "phone", header: "Phone", render: (c) => c.phone || <span className="muted">—</span> },
    { key: "source", header: "Source", sortable: true, render: (c) => SOURCE_LABELS[c.source] },
    { key: "applications_count", header: "Applications", sortable: true, align: "right", render: (c) => <span className="mono">{c.applications_count}</span> },
    { key: "created_at", header: "Added", sortable: true, render: (c) => formatDate(c.created_at) },
    { key: "actions", header: <span className="sr-only">Actions</span>, render: (c) => (
      <div className="cell-actions">
        {can("candidates:manage") && <IconButton icon={Pencil} label={`Edit ${c.full_name}`} onClick={() => setDialog({ type: "edit", candidate: c })} />}
        {can("candidates:manage") && <IconButton icon={Trash2} danger label={`Delete ${c.full_name}`} onClick={() => setDialog({ type: "delete", candidate: c })} />}
      </div>
    ) },
  ];

  const empty = filtersActive ? (
    <EmptyState title="No candidates match your filters" message="Try a different search term or clear the filters." action={<Button onClick={() => setF({ search: "", source: "" })}>Clear filters</Button>} />
  ) : (
    <EmptyState icon={Users} title="No candidates yet" message="Add a candidate to start building your talent pool." action={can("candidates:manage") && <Button variant="primary" icon={Plus} onClick={() => setDialog({ type: "create" })}>Add candidate</Button>} />
  );

  return (
    <>
      <PageHeader title="Candidates" description="Everyone in your talent pool, and the roles they have applied for." actions={can("candidates:manage") && <Button variant="primary" icon={Plus} onClick={() => setDialog({ type: "create" })}>Add candidate</Button>} />
      <div className="card">
        <FilterBar search={f.search} onSearch={(v) => setF({ ...f, search: v })} placeholder="Search name, email, ID…" searchLabel="Search candidates"
          active={!!filtersActive} onClear={() => setF({ search: "", source: "" })} count={data?.length} noun="candidate">
          <select className="select" aria-label="Filter by source" value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })}>
            <option value="">All sources</option>
            {meta.candidate_sources.map((s) => <option key={s} value={s}>{SOURCE_LABELS[s]}</option>)}
          </select>
        </FilterBar>
        <DataTable caption="Candidates" columns={columns} rows={data} loading={loading} error={error} onRetry={refetch} sort={sort} order={order} onSort={onSort} empty={empty} />
      </div>

      {(dialog?.type === "create" || dialog?.type === "edit") && (
        <CandidateFormDialog candidate={dialog.candidate} onClose={close} onSaved={() => { close(); refetch(); }} />
      )}
      {dialog?.type === "view" && (
        <CandidateDetailDialog candidate={dialog.candidate} refreshKey={detailKey} onClose={close}
          onEdit={(candidate) => setDialog({ type: "edit", candidate })} onApply={(candidate) => setDialog({ type: "apply", candidate })} />
      )}
      {dialog?.type === "apply" && (
        <ApplicationFormDialog candidateId={dialog.candidate.id} onClose={() => setDialog({ type: "view", candidate: dialog.candidate })}
          onSaved={() => { setDetailKey((k) => k + 1); setDialog({ type: "view", candidate: dialog.candidate }); refetch(); }} />
      )}
      {dialog?.type === "delete" && (
        <ConfirmDialog title="Delete this candidate?" onConfirm={() => remove(dialog.candidate)} onClose={close}>
          <p><strong>{dialog.candidate.full_name}</strong> will be removed permanently.</p>
          {dialog.candidate.applications_count > 0 && (
            <p style={{ marginTop: 8 }}>Their {dialog.candidate.applications_count} application{dialog.candidate.applications_count === 1 ? "" : "s"} will be deleted too.</p>
          )}
        </ConfirmDialog>
      )}
    </>
  );
}
