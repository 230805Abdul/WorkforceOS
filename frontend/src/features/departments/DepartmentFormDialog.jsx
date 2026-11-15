import { useState } from "react";
import Modal from "../../components/ui/Modal";
import { Button, FormAlert, FormField } from "../../components/ui";
import { useToast } from "../../components/ui/Toast";
import { useSubmit } from "../../hooks/useSubmit";
import { api } from "../../services/api";

const EMPTY = { name: "", code: "", description: "" };

/** Create (department = null) or edit a department. */
export default function DepartmentFormDialog({ department, onClose, onSaved }) {
  const toast = useToast();
  const [form, setForm] = useState(department ? { ...EMPTY, ...department, description: department.description ?? "" } : EMPTY);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const { submit, pending, errors, formError, formRef } = useSubmit(async () => {
    const body = { name: form.name, code: form.code, description: form.description };
    const saved = department ? await api.departments.update(department.id, body) : await api.departments.create(body);
    toast.success(department ? `“${saved.name}” was updated.` : `“${saved.name}” was created.`);
    onSaved(saved);
  });

  return (
    <Modal
      title={department ? "Edit department" : "New department"}
      description={department ? department.id : "Departments group your employees and the jobs you hire for."}
      onClose={onClose}
      busy={pending}
      footer={
        <>
          <Button onClick={onClose} disabled={pending}>Cancel</Button>
          <Button variant="primary" type="submit" form="department-form" loading={pending}>{department ? "Save changes" : "Create department"}</Button>
        </>
      }
    >
      <form id="department-form" ref={formRef} onSubmit={submit} noValidate>
        <FormAlert>{formError && !Object.keys(errors).length ? formError : ""}</FormAlert>
        <div className="form-grid">
          <FormField label="Name" required error={errors.name}>
            <input className="input" value={form.name} onChange={set("name")} placeholder="e.g. Customer Success" maxLength={80} />
          </FormField>
          <FormField label="Code" required error={errors.code} hint="2–10 letters or digits, e.g. CS. Must be unique.">
            <input className="input" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
              placeholder="CS" maxLength={10} style={{ textTransform: "uppercase" }} />
          </FormField>
          <FormField label="Description" error={errors.description} className="span-2">
            <textarea className="textarea" value={form.description} onChange={set("description")} placeholder="Optional: what does this team do?" maxLength={500} />
          </FormField>
        </div>
      </form>
    </Modal>
  );
}
