import Modal from "../../components/ui/Modal";
import { Button } from "../../components/ui";
import StatusBadge from "../../components/shared/StatusBadge";
import { EmptyState, ErrorState } from "../../components/shared/State";
import { useFetch } from "../../hooks/useFetch";
import { TYPE_LABELS, formatDate } from "../../lib/format";
import { api } from "../../services/api";
import { Pencil } from "lucide-react";
import { useAuth } from "../../auth/AuthContext";

export default function JobDetailDialog({ job, onClose, onEdit }) {
  const { can } = useAuth();
  const { data: apps, error, refetch } = useFetch((s) => (can("applications:read") ? api.applications.list({ job_id: job.id }, s) : Promise.resolve(null)), [job.id]);
  return (
    <Modal
      size="wide"
      title={job.title}
      description={`${job.id} · ${job.department}`}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Close</Button>
          {can("jobs:manage") && <Button variant="primary" icon={Pencil} onClick={() => onEdit(job)}>Edit job</Button>}
        </>
      }
    >
      <dl className="dl">
        <div><dt>Status</dt><dd><StatusBadge status={job.status} /></dd></div>
        <div><dt>Employment type</dt><dd>{TYPE_LABELS[job.employment_type]}</dd></div>
        <div><dt>Location</dt><dd>{job.location}</dd></div>
        <div><dt>Openings filled</dt><dd>{job.hired_count} of {job.openings}</dd></div>
        <div><dt>Created</dt><dd>{formatDate(job.created_at)}</dd></div>
        <div><dt>Last updated</dt><dd>{formatDate(job.updated_at)}</dd></div>
        <div className="span-2"><dt>Description</dt><dd style={{ fontWeight: 400 }}>{job.description}</dd></div>
      </dl>
      {can("applications:read") && <><h3 className="section-title">Applications</h3>
      {error ? <ErrorState error={error} onRetry={refetch} /> : !apps ? <div className="skeleton" /> : apps.length === 0 ? (
        <EmptyState title="No applications yet" message="Add one from the Candidates or Pipeline page." />
      ) : (
        <ul className="mini-list">
          {apps.map((a) => (
            <li key={a.id}>
              <div><strong>{a.candidate_name}</strong><span className="cell-sub">{a.candidate_email}</span></div>
              <StatusBadge status={a.status} />
            </li>
          ))}
        </ul>
      )}</>}
    </Modal>
  );
}
