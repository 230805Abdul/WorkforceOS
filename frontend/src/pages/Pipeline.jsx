import { useState } from "react";
import { ArrowRight, BadgeCheck, GitPullRequestArrow, Plus, Trash2, UserPlus, XCircle } from "lucide-react";
import { api } from "../services/api";
import { useFetch } from "../hooks/useFetch";
import { useDebounce } from "../hooks/useDebounce";
import PageHeader from "../components/shared/PageHeader";
import FilterBar from "../components/shared/FilterBar";
import ConfirmDialog from "../components/shared/ConfirmDialog";
import { EmptyState, ErrorState } from "../components/shared/State";
import { Button, IconButton } from "../components/ui";
import { useToast } from "../components/ui/Toast";
import ApplicationFormDialog from "../features/applications/ApplicationFormDialog";
import EmployeeFormDialog from "../features/employees/EmployeeFormDialog";
import { STATUS_LABELS, formatDate } from "../lib/format";
import { useMeta } from "../lib/MetaContext";
import { useAuth } from "../auth/AuthContext";

export default function Pipeline() {
  const { can } = useAuth();
  const manage = can("applications:manage");
  const meta = useMeta();
  const toast = useToast();
  const [f, setF] = useState({ search: "", job_id: "" });
  const [dialog, setDialog] = useState(null); // 'add' | { remove: application } | { reject: application } | { employ: application }
  const [movingId, setMovingId] = useState(null);
  const search = useDebounce(f.search);

  const jobs = useFetch((s) => (can("jobs:read") ? api.jobs.list({ sort: "title", order: "asc" }, s) : Promise.resolve([])), []);
  const { data, error, refetch } = useFetch((s) => api.applications.list({ search, job_id: f.job_id }, s), [search, f.job_id]);
  const close = () => setDialog(null);

  async function move(app, status) {
    if (movingId) return;
    setMovingId(app.id);
    try {
      await api.applications.updateStatus(app.id, status);
      toast.success(`${app.candidate_name} moved to ${STATUS_LABELS[status]}.`);
      refetch();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setMovingId(null);
    }
  }
  async function remove(app) {
    try {
      await api.applications.remove(app.id);
      toast.success(`Application for ${app.candidate_name} was removed.`);
      refetch();
    } catch (e) {
      toast.error(e.message);
    }
    close();
  }

  const active = f.search || f.job_id;
  const clear = () => setF({ search: "", job_id: "" });

  return (
    <>
      <PageHeader title="Pipeline" description="Track every application through the hiring stages. Applications move forward one stage at a time, or can be rejected."
        actions={manage && <Button variant="primary" icon={Plus} onClick={() => setDialog("add")}>Add application</Button>} />
      <div className="card" style={{ marginBottom: 16 }}>
        <FilterBar search={f.search} onSearch={(v) => setF({ ...f, search: v })} placeholder="Search candidate or job…" searchLabel="Search applications"
          active={!!active} onClear={clear} count={data?.length} noun="application">
          {can("jobs:read") && (
            <select className="select" aria-label="Filter by job" value={f.job_id} onChange={(e) => setF({ ...f, job_id: e.target.value })}>
              <option value="">All jobs</option>
              {(jobs.data ?? []).map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
            </select>
          )}
        </FilterBar>
      </div>

      {error && !data ? <div className="card"><ErrorState error={error} onRetry={refetch} /></div> : !data ? (
        <div className="card card-body" role="status" aria-label="Loading"><div className="skeleton" style={{ height: 120 }} /></div>
      ) : data.length === 0 ? (
        <div className="card">
          {active ? <EmptyState title="No applications match your filters" action={<Button onClick={clear}>Clear filters</Button>} />
            : <EmptyState icon={GitPullRequestArrow} title="No applications yet" message="Attach a candidate to an open job to start tracking them." action={manage && <Button variant="primary" icon={Plus} onClick={() => setDialog("add")}>Add application</Button>} />}
        </div>
      ) : (
        <div className="board">
          {meta.application_statuses.map((status) => {
            const items = data.filter((a) => a.status === status);
            return (
              <section key={status} className="column" aria-labelledby={`col-${status}`}>
                <div className="column-head"><h2 id={`col-${status}`} style={{ fontSize: 14 }}>{STATUS_LABELS[status]}</h2><span className="column-count" aria-label={`${items.length} applications`}>{items.length}</span></div>
                {items.length === 0 ? <p className="column-empty">Nothing in this stage</p> : (
                  <ul className="column-list">
                    {items.map((a) => {
                      const next = a.allowed_next.find((s) => s !== "rejected");
                      return (
                        <li key={a.id} className="pcard">
                          <div className="pcard-top">
                            <strong>{a.candidate_name}</strong>
                            {manage && <IconButton icon={Trash2} danger label={`Remove application for ${a.candidate_name}`} onClick={() => setDialog({ remove: a })} />}
                          </div>
                          <span>{a.job_title}</span>
                          <span className="cell-sub">{a.department} · updated {formatDate(a.updated_at)}</span>
                          {a.status === "hired" && (a.employee_id ? (
                            <span className="cell-sub" style={{ display: "inline-flex", gap: 4, alignItems: "center", marginTop: 6 }}>
                              <BadgeCheck size={14} aria-hidden="true" /> Employee record {a.employee_id}
                            </span>
                          ) : (
                            <div className="pcard-actions">
                              {can("employees:create") && can("departments:read") ? <Button size="sm" icon={UserPlus} onClick={() => setDialog({ employ: a })}>Create employee</Button> : <span className="cell-sub">Not yet an employee</span>}
                            </div>
                          ))}
                          {manage && a.allowed_next.length > 0 && (
                            <div className="pcard-actions">
                              {next && <Button size="sm" variant="primary" disabled={!!movingId} loading={movingId === a.id} onClick={() => move(a, next)}>{STATUS_LABELS[next]}<ArrowRight size={14} aria-hidden="true" /></Button>}
                              <Button size="sm" icon={XCircle} disabled={!!movingId} onClick={() => setDialog({ reject: a })}>Reject</Button>
                            </div>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </section>
            );
          })}
        </div>
      )}

      {dialog?.employ && (
        <EmployeeFormDialog fromCandidate={dialog.employ} onClose={close} onSaved={() => { close(); refetch(); }} />
      )}
      {dialog === "add" && <ApplicationFormDialog onClose={close} onSaved={() => { close(); refetch(); }} />}
      {dialog?.reject && (
        <ConfirmDialog title="Reject this application?" confirmLabel="Reject" onClose={close} onConfirm={async () => { await move(dialog.reject, "rejected"); close(); }}>
          <p><strong>{dialog.reject.candidate_name}</strong> will be marked as rejected for <strong>{dialog.reject.job_title}</strong>. This is a final stage.</p>
        </ConfirmDialog>
      )}
      {dialog?.remove && (
        <ConfirmDialog title="Remove this application?" confirmLabel="Remove" onClose={close} onConfirm={() => remove(dialog.remove)}>
          <p>The application of <strong>{dialog.remove.candidate_name}</strong> for <strong>{dialog.remove.job_title}</strong> will be deleted. The candidate stays in your talent pool.</p>
        </ConfirmDialog>
      )}
    </>
  );
}
