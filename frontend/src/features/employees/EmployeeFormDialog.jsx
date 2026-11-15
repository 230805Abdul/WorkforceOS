import { useEffect, useState } from "react";
import Modal from "../../components/ui/Modal";
import { Button, FormAlert, FormField } from "../../components/ui";
import { useToast } from "../../components/ui/Toast";
import DepartmentSelect from "../../components/shared/DepartmentSelect";
import { useDepartments } from "../../hooks/useDepartments";
import { useSubmit } from "../../hooks/useSubmit";
import { useMeta } from "../../lib/MetaContext";
import { STATUS_LABELS, todayIso } from "../../lib/format";
import { api } from "../../services/api";

const EMPTY = { employee_code: "", first_name: "", last_name: "", email: "", phone: "", job_title: "", department_id: "",
  employment_status: "active", joining_date: "" };

/** "Mei Lin Chen" -> { first_name: "Mei Lin", last_name: "Chen" } */
export function splitName(full = "") {
  const parts = full.trim().split(/\s+/);
  return parts.length > 1 ? { first_name: parts.slice(0, -1).join(" "), last_name: parts.at(-1) } : { first_name: parts[0] ?? "", last_name: "" };
}

/**
 * Create or edit an employee.
 * - employee: edit this record
 * - fromCandidate: { candidate_id, candidate_name, candidate_email, job_title, department_id } to turn a HIRED candidate into an employee
 */
export default function EmployeeFormDialog({ employee, fromCandidate, onClose, onSaved }) {
  const meta = useMeta();
  const toast = useToast();
  const departments = useDepartments();
  const [form, setForm] = useState(() => {
    if (employee) return { ...EMPTY, ...employee, phone: employee.phone ?? "" };
    const base = { ...EMPTY, joining_date: todayIso() };
    if (!fromCandidate) return base;
    return { ...base, ...splitName(fromCandidate.candidate_name), email: fromCandidate.candidate_email,
      job_title: fromCandidate.job_title, department_id: fromCandidate.department_id };
  });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  // New employee: suggest the next free code and default to the first department.
  useEffect(() => {
    if (employee) return;
    const ctrl = new AbortController();
    api.employees.nextCode(ctrl.signal).then((r) => setForm((f) => (f.employee_code ? f : { ...f, employee_code: r.employee_code }))).catch(() => {});
    return () => ctrl.abort();
  }, [employee]);
  useEffect(() => {
    if (!form.department_id && departments.data?.length) setForm((f) => ({ ...f, department_id: departments.data[0].id }));
  }, [departments.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const { submit, pending, errors, formError, formRef } = useSubmit(async () => {
    const body = { ...form };
    delete body.id; // keep only editable fields
    for (const k of ["full_name", "department", "candidate_id", "is_sample", "created_at", "updated_at"]) delete body[k];
    if (fromCandidate) body.candidate_id = fromCandidate.candidate_id;
    const saved = employee ? await api.employees.update(employee.id, body) : await api.employees.create(body);
    toast.success(employee ? `${saved.full_name} was updated.` : `${saved.full_name} was added as an employee.`);
    onSaved(saved);
  });

  const title = employee ? "Edit employee" : fromCandidate ? "Create employee record" : "Add employee";
  const description = employee ? `${employee.id} · ${employee.employee_code}`
    : fromCandidate ? `From hired candidate ${fromCandidate.candidate_name}. Check the details, then save.`
    : "Add a person who works here.";
  const noDepartments = departments.data && !departments.data.length;

  return (
    <Modal
      size="wide"
      title={title}
      description={description}
      onClose={onClose}
      busy={pending}
      footer={
        <>
          <Button onClick={onClose} disabled={pending}>Cancel</Button>
          <Button variant="primary" type="submit" form="employee-form" loading={pending} disabled={noDepartments}>
            {employee ? "Save changes" : "Add employee"}
          </Button>
        </>
      }
    >
      <form id="employee-form" ref={formRef} onSubmit={submit} noValidate>
        <FormAlert>{formError && (!Object.keys(errors).length || errors.candidate_id) ? (errors.candidate_id || formError) : ""}</FormAlert>
        <div className="form-grid">
          <FormField label="First name" required error={errors.first_name}>
            <input className="input" value={form.first_name} onChange={set("first_name")} maxLength={60} autoComplete="off" />
          </FormField>
          <FormField label="Last name" required error={errors.last_name}>
            <input className="input" value={form.last_name} onChange={set("last_name")} maxLength={60} autoComplete="off" />
          </FormField>
          <FormField label="Email" required error={errors.email}>
            <input className="input" type="email" value={form.email} onChange={set("email")} autoComplete="off" />
          </FormField>
          <FormField label="Phone" error={errors.phone} hint="Optional. Digits, spaces, + ( ) -">
            <input className="input" type="tel" value={form.phone} onChange={set("phone")} autoComplete="off" />
          </FormField>
          <FormField label="Employee code" required error={errors.employee_code} hint="Unique, e.g. E-0014.">
            <input className="input mono" value={form.employee_code} onChange={(e) => setForm({ ...form, employee_code: e.target.value.toUpperCase() })} maxLength={20} />
          </FormField>
          <FormField label="Job title" required error={errors.job_title}>
            <input className="input" value={form.job_title} onChange={set("job_title")} maxLength={120} />
          </FormField>
          <FormField label="Department" required error={errors.department_id}
            hint={noDepartments ? "Create a department first (Workforce → Departments)." : undefined}>
            <DepartmentSelect departments={departments} value={form.department_id} onChange={set("department_id")}
              placeholder={departments.data?.length ? undefined : "No departments yet"} />
          </FormField>
          <FormField label="Status" error={errors.employment_status}>
            <select className="select" value={form.employment_status} onChange={set("employment_status")}>
              {meta.employment_statuses.map((s) => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
            </select>
          </FormField>
          <FormField label="Joining date" required error={errors.joining_date}>
            <input className="input" type="date" value={form.joining_date} onChange={set("joining_date")} />
          </FormField>
        </div>
      </form>
    </Modal>
  );
}
