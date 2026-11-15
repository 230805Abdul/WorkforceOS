import { useState } from "react";
import { Briefcase, Pencil, Plus, Trash2 } from "lucide-react";
import { api } from "../services/api";
import { useFetch } from "../hooks/useFetch";
import { useDebounce } from "../hooks/useDebounce";
import { useMeta } from "../lib/MetaContext";
import { useDepartments } from "../hooks/useDepartments";
import DepartmentSelect from "../components/shared/DepartmentSelect";
import PageHeader from "../components/shared/PageHeader";
import FilterBar from "../components/shared/FilterBar";
import DataTable from "../components/shared/DataTable";
import StatusBadge from "../components/shared/StatusBadge";
import ConfirmDialog from "../components/shared/ConfirmDialog";
import { EmptyState } from "../components/shared/State";
import { Button, IconButton } from "../components/ui";
import { useToast } from "../components/ui/Toast";
import JobFormDialog from "../features/jobs/JobFormDialog";
import JobDetailDialog from "../features/jobs/JobDetailDialog";
import { STATUS_LABELS, TYPE_LABELS, formatDate } from "../lib/format";
import { useAuth } from "../auth/AuthContext";

export default function Jobs() {
  const { can } = useAuth();
  const meta = useMeta();
  const toast = useToast();
  const [f, setF] = useState({ search: "", status: "", department_id: "" });
  const [sort, setSort] = useState("created_at");
  const [order, setOrder] = useState("desc");
  const [dialog, setDialog] = useState(null); // { type: 'create'|'edit'|'view'|'delete', job? }
  const search = useDebounce(f.search);
  const departments = useDepartments();

  const { data, error, loading, refetch } = useFetch(
    (s) => api.jobs.list({ search, status: f.status, department_id: f.department_id, sort, order }, s),
    [search, f.status, f.department_id, sort, order]
  );

  const onSort = (key) => {
    if (key === sort) setOrder(order === "asc" ? "desc" : "asc");
    else { setSort(key); setOrder("asc"); }
  };
  const close = () => setDialog(null);
  const saved = () => { close(); refetch(); };
  const filtersActive = f.search || f.status || f.department_id;

  async function remove(job) {
    try {
      await api.jobs.remove(job.id);
      toast.success(`“${job.title}” was deleted.`);
      close();
      refetch();
    } catch (e) {
      toast.error(e.message);
      close();
    }
  }

  const columns = [
    { key: "title", header: "Job", sortable: true, render: (j) => (
      <><button type="button" className="link-btn" onClick={() => setDialog({ type: "view", job: j })}>{j.title}</button><div className="cell-sub">{j.id} · {j.location}</div></>
    ) },
    { key: "department", header: "Department", sortable: true },
    { key: "employment_type", header: "Type", render: (j) => TYPE_LABELS[j.employment_type] },
    { key: "status", header: "Status", sortable: true, render: (j) => <StatusBadge status={j.status} /> },
    { key: "openings", header: "Filled", sortable: true, render: (j) => <span className="mono">{j.hired_count} / {j.openings}</span> },
    { key: "applications_count", header: "Applicants", sortable: true, align: "right", render: (j) => <span className="mono">{j.applications_count}</span> },
    { key: "created_at", header: "Created", sortable: true, render: (j) => formatDate(j.created_at) },
    { key: "actions", header: <span className="sr-only">Actions</span>, render: (j) => (
      <div className="cell-actions">
        {can("jobs:manage") && <IconButton icon={Pencil} label={`Edit ${j.title}`} onClick={() => setDialog({ type: "edit", job: j })} />}
        {can("jobs:manage") && <IconButton icon={Trash2} danger label={`Delete ${j.title}`} onClick={() => setDialog({ type: "delete", job: j })} />}
      </div>
    ) },
  ];

  const empty = filtersActive ? (
    <EmptyState title="No jobs match your filters" message="Try a different search term or clear the filters." action={<Button onClick={() => setF({ search: "", status: "", department_id: "" })}>Clear filters</Button>} />
  ) : (
    <EmptyState icon={Briefcase} title="No jobs yet" message="Create your first job to start collecting applications." action={can("jobs:manage") && <Button variant="primary" icon={Plus} onClick={() => setDialog({ type: "create" })}>New job</Button>} />
  );

  return (
    <>
      <PageHeader title="Jobs" description="Create and manage the roles you are hiring for." actions={can("jobs:manage") && <Button variant="primary" icon={Plus} onClick={() => setDialog({ type: "create" })}>New job</Button>} />
      <div className="card">
        <FilterBar search={f.search} onSearch={(v) => setF({ ...f, search: v })} placeholder="Search title, ID, location…" searchLabel="Search jobs"
          active={!!filtersActive} onClear={() => setF({ search: "", status: "", department_id: "" })} count={data?.length} noun="job">
          <select className="select" aria-label="Filter by status" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
            <option value="">All statuses</option>
            {meta.job_statuses.map((s) => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
          </select>
          <DepartmentSelect departments={departments} aria-label="Filter by department" placeholder="All departments"
            value={f.department_id} onChange={(e) => setF({ ...f, department_id: e.target.value })} />
        </FilterBar>
        <DataTable caption="Jobs" columns={columns} rows={data} loading={loading} error={error} onRetry={refetch} sort={sort} order={order} onSort={onSort} empty={empty} />
      </div>

      {(dialog?.type === "create" || dialog?.type === "edit") && <JobFormDialog job={dialog.job} onClose={close} onSaved={saved} />}
      {dialog?.type === "view" && <JobDetailDialog job={dialog.job} onClose={close} onEdit={(job) => setDialog({ type: "edit", job })} />}
      {dialog?.type === "delete" && (
        <ConfirmDialog title="Delete this job?" onConfirm={() => remove(dialog.job)} onClose={close}>
          <p><strong>{dialog.job.title}</strong> will be removed permanently.</p>
          {dialog.job.applications_count > 0 && (
            <p style={{ marginTop: 8 }}>Its {dialog.job.applications_count} application{dialog.job.applications_count === 1 ? "" : "s"} will be deleted too. To keep the history, set the job to Closed or Archived instead.</p>
          )}
        </ConfirmDialog>
      )}
    </>
  );
}
