import { useState } from "react";
import Modal from "../../components/ui/Modal";
import { Button, FormAlert, FormField } from "../../components/ui";
import { useToast } from "../../components/ui/Toast";
import { useMeta } from "../../lib/MetaContext";
import { useSubmit } from "../../hooks/useSubmit";
import { SOURCE_LABELS } from "../../lib/format";
import { api } from "../../services/api";

const EMPTY = { full_name: "", email: "", phone: "", source: "careers_page" };

export default function CandidateFormDialog({ candidate, onClose, onSaved }) {
  const meta = useMeta();
  const toast = useToast();
  const [form, setForm] = useState(candidate ? { ...EMPTY, ...candidate, phone: candidate.phone ?? "" } : EMPTY);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const { submit, pending, errors, formError, formRef } = useSubmit(async () => {
    const body = Object.fromEntries(Object.keys(EMPTY).map((k) => [k, form[k]])); // editable fields only
    const saved = candidate ? await api.candidates.update(candidate.id, body) : await api.candidates.create(body);
    toast.success(candidate ? `${saved.full_name} was updated.` : `${saved.full_name} was added.`);
    onSaved(saved);
  });

  return (
    <Modal
      title={candidate ? "Edit candidate" : "Add candidate"}
      description={candidate ? candidate.id : "Add a person to your talent pool. You can attach them to a job afterwards."}
      onClose={onClose}
      busy={pending}
      footer={
        <>
          <Button onClick={onClose} disabled={pending}>Cancel</Button>
          <Button variant="primary" type="submit" form="candidate-form" loading={pending}>{candidate ? "Save changes" : "Add candidate"}</Button>
        </>
      }
    >
      <form id="candidate-form" ref={formRef} onSubmit={submit} noValidate>
        <FormAlert>{formError && !Object.keys(errors).length ? formError : ""}</FormAlert>
        <div className="form-grid">
          <FormField label="Full name" required error={errors.full_name} className="span-2">
            <input className="input" value={form.full_name} onChange={set("full_name")} autoComplete="off" />
          </FormField>
          <FormField label="Email" required error={errors.email}>
            <input className="input" type="email" value={form.email} onChange={set("email")} autoComplete="off" />
          </FormField>
          <FormField label="Phone" error={errors.phone} hint="Optional. Digits, spaces, + ( ) -">
            <input className="input" type="tel" value={form.phone} onChange={set("phone")} autoComplete="off" />
          </FormField>
          <FormField label="Source" error={errors.source} className="span-2">
            <select className="select" value={form.source} onChange={set("source")}>
              {meta.candidate_sources.map((s) => <option key={s} value={s}>{SOURCE_LABELS[s]}</option>)}
            </select>
          </FormField>
        </div>
      </form>
    </Modal>
  );
}
