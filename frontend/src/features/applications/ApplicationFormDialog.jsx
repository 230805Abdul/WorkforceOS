import { useState } from "react";
import Modal from "../../components/ui/Modal";
import { Button, FormAlert, FormField } from "../../components/ui";
import { useToast } from "../../components/ui/Toast";
import { ErrorState } from "../../components/shared/State";
import { useFetch } from "../../hooks/useFetch";
import { useSubmit } from "../../hooks/useSubmit";
import { api } from "../../services/api";

/** Attach a candidate to an open job. Either side can be preset (and then locked). */
export default function ApplicationFormDialog({ candidateId = "", jobId = "", onClose, onSaved }) {
  const toast = useToast();
  const [form, setForm] = useState({ candidate_id: candidateId, job_id: jobId });
  const candidates = useFetch((s) => api.candidates.list({ sort: "full_name", order: "asc" }, s), []);
  const jobs = useFetch((s) => api.jobs.list({ status: "open", sort: "title", order: "asc" }, s), []);

  const { submit, pending, errors, formError, formRef } = useSubmit(async () => {
    const saved = await api.applications.create(form);
    toast.success(`${saved.candidate_name} was added to “${saved.job_title}”.`);
    onSaved(saved);
  });
  const loadError = candidates.error || jobs.error;
  const ready = candidates.data && jobs.data;

  return (
    <Modal
      title="Add application"
      description="Only open jobs are listed. A candidate can apply to each job once."
      onClose={onClose}
      busy={pending}
      footer={
        <>
          <Button onClick={onClose} disabled={pending}>Cancel</Button>
          <Button variant="primary" type="submit" form="application-form" loading={pending} disabled={!ready}>Add application</Button>
        </>
      }
    >
      {loadError ? <ErrorState error={loadError} onRetry={() => { candidates.refetch(); jobs.refetch(); }} /> : !ready ? <div className="skeleton" /> : (
        <form id="application-form" ref={formRef} onSubmit={submit} noValidate>
          <FormAlert>{formError && !Object.keys(errors).length ? formError : ""}</FormAlert>
          <div className="form-grid">
            <FormField label="Candidate" required error={errors.candidate_id} className="span-2">
              <select className="select" value={form.candidate_id} disabled={!!candidateId} onChange={(e) => setForm({ ...form, candidate_id: e.target.value })}>
                <option value="">Select a candidate…</option>
                {candidates.data.map((c) => <option key={c.id} value={c.id}>{c.full_name} — {c.email}</option>)}
              </select>
            </FormField>
            <FormField label="Job" required error={errors.job_id} className="span-2">
              <select className="select" value={form.job_id} disabled={!!jobId} onChange={(e) => setForm({ ...form, job_id: e.target.value })}>
                <option value="">Select an open job…</option>
                {jobs.data.map((j) => <option key={j.id} value={j.id}>{j.title} — {j.department}</option>)}
              </select>
            </FormField>
          </div>
        </form>
      )}
    </Modal>
  );
}
