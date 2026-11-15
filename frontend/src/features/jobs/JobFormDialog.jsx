import { useEffect, useState } from "react";
import Modal from "../../components/ui/Modal";
import { Button, FormAlert, FormField } from "../../components/ui";
import { useToast } from "../../components/ui/Toast";
import { useMeta } from "../../lib/MetaContext";
import { useSubmit } from "../../hooks/useSubmit";
import { useDepartments } from "../../hooks/useDepartments";
import DepartmentSelect from "../../components/shared/DepartmentSelect";
import { STATUS_LABELS, TYPE_LABELS } from "../../lib/format";
import { api } from "../../services/api";

const EMPTY = { title: "", department_id: "", location: "", employment_type: "full_time", status: "draft", openings: 1, description: "" };

/** Create (job = null) or edit a job. */
export default function JobFormDialog({ job, onClose, onSaved }) {
  const meta = useMeta();
  const toast = useToast();
  const [form, setForm] = useState(job ? { ...EMPTY, ...job } : EMPTY);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const departments = useDepartments();
  // New job: pre-select the first department once the list has loaded.
  useEffect(() => {
    if (!form.department_id && departments.data?.length) setForm((f) => ({ ...f, department_id: departments.data[0].id }));
  }, [departments.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const { submit, pending, errors, formError, formRef } = useSubmit(async () => {
    // Only the editable fields: the API rejects unknown ones (ids, counts...) instead of silently ignoring them.
    const body = Object.fromEntries(Object.keys(EMPTY).map((k) => [k, form[k]]));
    body.openings = form.openings === "" ? "" : Number(form.openings);
    const saved = job ? await api.jobs.update(job.id, body) : await api.jobs.create(body);
    toast.success(job ? `“${saved.title}” was updated.` : `“${saved.title}” was created.`);
    onSaved(saved);
  });

  return (
    <Modal
      title={job ? "Edit job" : "New job"}
      description={job ? job.id : "Create a role to start collecting applications. Only open jobs accept applications."}
      onClose={onClose}
      busy={pending}
      footer={
        <>
          <Button onClick={onClose} disabled={pending}>Cancel</Button>
          <Button variant="primary" type="submit" form="job-form" loading={pending}>{job ? "Save changes" : "Create job"}</Button>
        </>
      }
    >
      <form id="job-form" ref={formRef} onSubmit={submit} noValidate>
        <FormAlert>{formError && !Object.keys(errors).length ? formError : ""}</FormAlert>
        <div className="form-grid">
          <FormField label="Job title" required error={errors.title} className="span-2">
            <input className="input" value={form.title} onChange={set("title")} placeholder="e.g. Senior Data Analyst" maxLength={120} />
          </FormField>
          <FormField label="Department" required error={errors.department_id}
            hint={departments.data && !departments.data.length ? "Create a department first (Workforce → Departments)." : undefined}>
            <DepartmentSelect departments={departments} value={form.department_id} onChange={set("department_id")}
              placeholder={departments.data?.length ? undefined : "No departments yet"} />
          </FormField>
          <FormField label="Location" required error={errors.location}>
            <input className="input" value={form.location} onChange={set("location")} placeholder="e.g. Remote (EU)" maxLength={100} />
          </FormField>
          <FormField label="Employment type" error={errors.employment_type}>
            <select className="select" value={form.employment_type} onChange={set("employment_type")}>
              {meta.employment_types.map((t) => <option key={t} value={t}>{TYPE_LABELS[t]}</option>)}
            </select>
          </FormField>
          <FormField label="Status" error={errors.status} hint="Draft jobs are hidden from the apply flow.">
            <select className="select" value={form.status} onChange={set("status")}>
              {meta.job_statuses.map((s) => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
            </select>
          </FormField>
          <FormField label="Openings" required error={errors.openings} hint="How many people you plan to hire.">
            <input className="input" type="number" min="1" max="50" value={form.openings} onChange={set("openings")} />
          </FormField>
          <FormField label="Description" required error={errors.description} className="span-2">
            <textarea className="textarea" value={form.description} onChange={set("description")} placeholder="What will this person do?" />
          </FormField>
        </div>
      </form>
    </Modal>
  );
}
