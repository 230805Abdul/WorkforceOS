import { Pencil, Plus } from "lucide-react";
import Modal from "../../components/ui/Modal";
import { Button } from "../../components/ui";
import StatusBadge from "../../components/shared/StatusBadge";
import { EmptyState, ErrorState } from "../../components/shared/State";
import { useFetch } from "../../hooks/useFetch";
import { SOURCE_LABELS, formatDate } from "../../lib/format";
import { api } from "../../services/api";
import { useAuth } from "../../auth/AuthContext";

export default function CandidateDetailDialog({ candidate, onClose, onEdit, onApply, refreshKey }) {
  const { can } = useAuth();
  const { data, error, refetch } = useFetch((s) => api.candidates.get(candidate.id, s), [candidate.id, refreshKey]);
  const c = data ?? candidate;
  return (
    <Modal
      size="wide"
      title={c.full_name}
      description={c.id}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Close</Button>
          {can("candidates:manage") && <Button icon={Pencil} onClick={() => onEdit(c)}>Edit</Button>}
          {can("applications:manage") && <Button variant="primary" icon={Plus} onClick={() => onApply(c)}>Add to job</Button>}
        </>
      }
    >
      <dl className="dl">
        <div><dt>Email</dt><dd>{c.email}</dd></div>
        <div><dt>Phone</dt><dd>{c.phone || "—"}</dd></div>
        <div><dt>Source</dt><dd>{SOURCE_LABELS[c.source]}</dd></div>
        <div><dt>Added</dt><dd>{formatDate(c.created_at)}</dd></div>
      </dl>
      <h3 className="section-title">Applications</h3>
      {error ? <ErrorState error={error} onRetry={refetch} /> : !data ? <div className="skeleton" /> : data.applications.length === 0 ? (
        <EmptyState title="No applications yet" message="Use “Add to job” to attach this candidate to an open role." />
      ) : (
        <ul className="mini-list">
          {data.applications.map((a) => (
            <li key={a.id}>
              <div><strong>{a.job_title}</strong><span className="cell-sub">{a.department} · applied {formatDate(a.created_at)}</span></div>
              <StatusBadge status={a.status} />
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}
