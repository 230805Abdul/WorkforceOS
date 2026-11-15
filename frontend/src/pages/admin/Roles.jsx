import { useState } from "react";
import { Lock, Pencil, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { api } from "../../services/api";
import { useFetch } from "../../hooks/useFetch";
import { useAuth } from "../../auth/AuthContext";
import PageHeader from "../../components/shared/PageHeader";
import ConfirmDialog from "../../components/shared/ConfirmDialog";
import { EmptyState, ErrorState } from "../../components/shared/State";
import Modal from "../../components/ui/Modal";
import { Badge, Button, FormAlert, FormField, IconButton } from "../../components/ui";
import { useToast } from "../../components/ui/Toast";
import { useSubmit } from "../../hooks/useSubmit";

function groupPermissions(permissions) {
  const groups = new Map();
  for (const p of permissions) groups.set(p.group, [...(groups.get(p.group) ?? []), p]);
  return [...groups.entries()];
}

function RoleDialog({ role, permissions, onClose, onSaved }) {
  const { can } = useAuth();
  const toast = useToast();
  const [form, setForm] = useState({ name: role?.name ?? "", label: role?.label ?? "", description: role?.description ?? "",
    permissions: role?.permissions ?? [] });
  const readOnly = !can("roles:manage");
  const locked = role?.locked || readOnly;
  const toggle = (code) => setForm({ ...form, permissions: form.permissions.includes(code)
    ? form.permissions.filter((c) => c !== code) : [...form.permissions, code] });

  const { submit, pending, errors, formError, formRef } = useSubmit(async () => {
    const body = { label: form.label, description: form.description || null, permissions: form.permissions };
    const saved = role ? await api.roles.update(role.id, body) : await api.roles.create({ ...body, name: form.name });
    toast.success(`“${saved.label}” was saved. Users with this role get the change on their next click.`);
    onSaved();
  });

  return (
    <Modal size="wide" title={role ? `Edit role: ${role.label}` : "New role"}
      description={role ? `${role.name} · ${role.users_count} user(s)` : "A role is a named set of permissions. Assign it to users on the Users page."}
      onClose={onClose} busy={pending}
      footer={readOnly ? <Button onClick={onClose}>Close</Button> : <><Button onClick={onClose} disabled={pending}>Cancel</Button>
        <Button variant="primary" type="submit" form="role-form" loading={pending}>{role ? "Save role" : "Create role"}</Button></>}>
      <form id="role-form" ref={formRef} onSubmit={submit} noValidate className="stack">
        <FormAlert>{formError && !Object.keys(errors).length ? formError : (errors.permissions ? `Permissions: ${errors.permissions}` : "")}</FormAlert>
        <div className="form-grid">
          <FormField label="Display name" required error={errors.label}>
            <input className="input" value={form.label} readOnly={readOnly} onChange={(e) => setForm({ ...form, label: e.target.value })} maxLength={60} />
          </FormField>
          <FormField label="Machine name" required={!role} error={errors.name} hint={role ? "Can't be changed." : "Lowercase letters, digits and _, e.g. payroll_viewer."}>
            <input className="input mono" value={form.name} readOnly={!!role} onChange={(e) => setForm({ ...form, name: e.target.value.toLowerCase() })} maxLength={40} />
          </FormField>
          <FormField label="Description" error={errors.description} className="span-2">
            <input className="input" value={form.description} readOnly={readOnly} onChange={(e) => setForm({ ...form, description: e.target.value })} maxLength={300} />
          </FormField>
        </div>
        {role?.locked && <div className="warning-box"><Lock size={16} aria-hidden="true" /> The Super Administrator role always has every permission, so the system can never be left without an administrator.</div>}
        <div className="perm-grid">
          {groupPermissions(permissions).map(([group, list]) => (
            <fieldset key={group} className="perm-group" style={{ border: 0, padding: 0, margin: 0 }}>
              <legend className="sr-only">{group}</legend>
              <h3 aria-hidden="true">{group}</h3>
              {list.map((p) => (
                <label key={p.code} className="perm-row" htmlFor={`perm-${p.code}`}>
                  <input id={`perm-${p.code}`} type="checkbox" checked={form.permissions.includes(p.code)} onChange={() => toggle(p.code)}
                    disabled={locked || !can(p.code)} />
                  <span>{p.description} <code>{p.code}</code>{!can(p.code) && !locked && <span className="cell-sub"> (you don't have this one, so you can't grant it)</span>}</span>
                </label>
              ))}
            </fieldset>
          ))}
        </div>
      </form>
    </Modal>
  );
}

export default function Roles() {
  const { can } = useAuth();
  const toast = useToast();
  const roles = useFetch((s) => api.roles.list(s), []);
  const permissions = useFetch((s) => api.roles.permissions(s), []);
  const [dialog, setDialog] = useState(null); // { edit: role } | "new" | { remove: role }
  const close = () => setDialog(null);
  const total = permissions.data?.length ?? 0;

  async function remove(role) {
    try {
      await api.roles.remove(role.id);
      toast.success(`“${role.label}” was deleted.`);
      roles.refetch();
    } catch (e) {
      toast.error(e.message);
    }
    close();
  }

  let body;
  if (roles.error || permissions.error) body = <div className="card"><ErrorState error={roles.error || permissions.error} onRetry={() => { roles.refetch(); permissions.refetch(); }} /></div>;
  else if (!roles.data || !permissions.data) body = <div className="card card-body"><div className="skeleton" style={{ height: 120 }} /></div>;
  else if (!roles.data.length) body = <div className="card"><EmptyState icon={ShieldCheck} title="No roles" /></div>;
  else body = (
    <div className="card">
      <ul className="mini-list" style={{ padding: "4px 20px 12px" }}>
        {roles.data.map((r) => (
          <li key={r.id}>
            <div>
              <strong>{r.label}</strong> {r.is_system && <Badge>Built-in</Badge>} {r.locked && <Badge tone="warning">Locked</Badge>}
              <span className="cell-sub">{r.description || r.name} · {r.permissions.length}/{total} permissions · {r.users_count} user{r.users_count === 1 ? "" : "s"}</span>
            </div>
            <div className="cell-actions">
              <IconButton icon={can("roles:manage") ? Pencil : ShieldCheck} label={`${can("roles:manage") ? "Edit" : "View"} ${r.label}`} onClick={() => setDialog({ edit: r })} />
              {can("roles:manage") && !r.is_system && <IconButton icon={Trash2} danger label={`Delete ${r.label}`} onClick={() => setDialog({ remove: r })} />}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );

  return (
    <>
      <PageHeader title="Roles & permissions"
        description="Permissions are fine-grained rights checked by the server on every request. Roles bundle them; a user's rights are the sum of their roles."
        actions={can("roles:manage") && <Button variant="primary" icon={Plus} onClick={() => setDialog("new")} disabled={!permissions.data}>New role</Button>} />
      {body}
      {(dialog === "new" || dialog?.edit) && (
        <RoleDialog role={dialog.edit} permissions={permissions.data} onClose={close} onSaved={() => { close(); roles.refetch(); }} />
      )}
      {dialog?.remove && (
        <ConfirmDialog title="Delete this role?" onConfirm={() => remove(dialog.remove)} onClose={close}>
          <p><strong>{dialog.remove.label}</strong> will be removed. Roles still assigned to someone can't be deleted.</p>
        </ConfirmDialog>
      )}
    </>
  );
}
