import { Pencil } from "lucide-react";
import Modal from "../../components/ui/Modal";
import { Button } from "../../components/ui";
import StatusBadge from "../../components/shared/StatusBadge";
import SampleTag from "../../components/shared/SampleTag";
import { formatDate, formatDay } from "../../lib/format";
import { useAuth } from "../../auth/AuthContext";

export default function EmployeeDetailDialog({ employee: e, onClose, onEdit }) {
  const { can } = useAuth();
  return (
    <Modal
      title={<>{e.full_name}<SampleTag show={e.is_sample} /></>}
      description={`${e.employee_code} · ${e.id}`}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Close</Button>
          {can("employees:update") && <Button variant="primary" icon={Pencil} onClick={() => onEdit(e)}>Edit employee</Button>}
        </>
      }
    >
      <dl className="dl">
        <div><dt>Status</dt><dd><StatusBadge status={e.employment_status} /></dd></div>
        <div><dt>Job title</dt><dd>{e.job_title}</dd></div>
        <div><dt>Department</dt><dd>{e.department}</dd></div>
        <div><dt>Joined</dt><dd>{formatDay(e.joining_date)}</dd></div>
        <div><dt>Email</dt><dd>{e.email}</dd></div>
        <div><dt>Phone</dt><dd>{e.phone || "—"}</dd></div>
        <div><dt>Hired through recruiting</dt><dd>{e.candidate_id ? `Yes (candidate ${e.candidate_id})` : "No"}</dd></div>
        <div><dt>Last updated</dt><dd>{formatDate(e.updated_at)}</dd></div>
      </dl>
    </Modal>
  );
}
