import { Pencil } from "lucide-react";
import Modal from "../../components/ui/Modal";
import { Button } from "../../components/ui";
import StatusBadge from "../../components/shared/StatusBadge";
import SampleTag from "../../components/shared/SampleTag";
import { EmptyState, ErrorState } from "../../components/shared/State";
import { useFetch } from "../../hooks/useFetch";
import { formatDate } from "../../lib/format";
import { api } from "../../services/api";
import { useAuth } from "../../auth/AuthContext";

export default function DepartmentDetailDialog({ department: d, onClose, onEdit }) {
  const { can } = useAuth();
  const employees = useFetch((s) => (can("employees:read") ? api.employees.list({ department_id: d.id, sort: "name" }, s) : Promise.resolve(null)), [d.id]);
  const jobs = useFetch((s) => (can("jobs:read") ? api.jobs.list({ department_id: d.id, sort: "title", order: "asc" }, s) : Promise.resolve(null)), [d.id]);

  return (
    <Modal
      size="wide"
      title={<>{d.name}<SampleTag show={d.is_sample} /></>}
      description={`${d.code} · ${d.id} · created ${formatDate(d.created_at)}`}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Close</Button>
          {can("departments:manage") && <Button variant="primary" icon={Pencil} onClick={() => onEdit(d)}>Edit department</Button>}
        </>
      }
    >
      {d.description && <p style={{ marginBottom: 16 }}>{d.description}</p>}
      <div className="stat-strip">
        <div><strong>{d.employees_count}</strong><span>Employees</span></div>
        <div><strong>{d.active_employees_count}</strong><span>Active</span></div>
        <div><strong>{d.jobs_count}</strong><span>Jobs</span></div>
      </div>

      {can("employees:read") && <>
      <h3 className="section-title">Employees</h3>
      {employees.error ? <ErrorState error={employees.error} onRetry={employees.refetch} /> : !employees.data ? <div className="skeleton" /> :
        employees.data.length === 0 ? <EmptyState title="No employees in this department" /> : (
          <ul className="mini-list" style={{ marginBottom: 18 }}>
            {employees.data.map((e) => (
              <li key={e.id}>
                <div><strong>{e.full_name}</strong><span className="cell-sub">{e.employee_code} · {e.job_title}</span></div>
                <StatusBadge status={e.employment_status} />
              </li>
            ))}
          </ul>
        )}

      </>}
      {can("jobs:read") && <>
      <h3 className="section-title">Jobs</h3>
      {jobs.error ? <ErrorState error={jobs.error} onRetry={jobs.refetch} /> : !jobs.data ? <div className="skeleton" /> :
        jobs.data.length === 0 ? <EmptyState title="No jobs in this department" /> : (
          <ul className="mini-list">
            {jobs.data.map((j) => (
              <li key={j.id}>
                <div><strong>{j.title}</strong><span className="cell-sub">{j.location} · {j.applications_count} applicant{j.applications_count === 1 ? "" : "s"}</span></div>
                <StatusBadge status={j.status} />
              </li>
            ))}
          </ul>
        )}
      </>}
    </Modal>
  );
}
