import { useState } from "react";
import Modal from "../../components/ui/Modal";
import { Button, FormAlert, FormField } from "../../components/ui";
import { useToast } from "../../components/ui/Toast";
import { useAuth } from "../../auth/AuthContext";
import { useFetch } from "../../hooks/useFetch";
import { useSubmit } from "../../hooks/useSubmit";
import { api } from "../../services/api";
import LinkBox from "./LinkBox";
import RoleCheckboxes from "./RoleCheckboxes";

/** Create an account without a password; the person sets their own with the one-time invitation link. */
export default function InviteUserDialog({ roles, onClose, onSaved }) {
  const { can } = useAuth();
  const toast = useToast();
  const employeeRole = roles.find((r) => r.name === "employee");
  const [form, setForm] = useState({ full_name: "", email: "", role_ids: employeeRole ? [employeeRole.id] : [], employee_id: "" });
  const [result, setResult] = useState(null);
  const employees = useFetch((s) => (can("employees:read") ? api.employees.list({ sort: "name" }, s) : Promise.resolve([])), []);

  const { submit, pending, errors, formError, formRef } = useSubmit(async () => {
    const r = await api.users.invite({ ...form, employee_id: form.employee_id || null });
    toast.success(`${r.user.full_name} was invited.`);
    setResult(r);
    onSaved();
  });

  return (
    <Modal size="wide" title={result ? "Invitation ready" : "Invite user"}
      description={result ? `${result.user.full_name} <${result.user.email}>` : "The account is created without a password. You'll get a one-time link to send them."}
      onClose={onClose} busy={pending}
      footer={result ? <Button variant="primary" onClick={onClose}>Done</Button> : (
        <><Button onClick={onClose} disabled={pending}>Cancel</Button>
          <Button variant="primary" type="submit" form="invite-form" loading={pending}>Create invitation</Button></>
      )}>
      {result ? <LinkBox link={result.invite} label="Invitation link (lets them choose a password)" /> : (
        <form id="invite-form" ref={formRef} onSubmit={submit} noValidate className="stack">
          <FormAlert>{formError && !Object.keys(errors).length ? formError : ""}</FormAlert>
          <div className="form-grid">
            <FormField label="Full name" required error={errors.full_name}>
              <input className="input" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} maxLength={120} />
            </FormField>
            <FormField label="Email" required error={errors.email}>
              <input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </FormField>
          </div>
          {can("employees:read") && (
            <FormField label="Linked employee record" error={errors.employee_id} hint="Optional. Lets them see their own record under My profile.">
              <select className="select" value={form.employee_id} onChange={(e) => setForm({ ...form, employee_id: e.target.value })}>
                <option value="">No linked employee</option>
                {(employees.data ?? []).map((e) => <option key={e.id} value={e.id}>{e.full_name} ({e.employee_code})</option>)}
              </select>
            </FormField>
          )}
          {can("roles:assign") && (
            <div>
              <h3 className="section-title">Roles {errors.role_ids && <span className="field-error">{errors.role_ids}</span>}</h3>
              <RoleCheckboxes roles={roles} value={form.role_ids} onChange={(role_ids) => setForm({ ...form, role_ids })} idPrefix="invite-role" />
            </div>
          )}
        </form>
      )}
    </Modal>
  );
}
