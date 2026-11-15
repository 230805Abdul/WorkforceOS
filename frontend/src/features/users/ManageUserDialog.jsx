import { useState } from "react";
import { KeyRound, LogOut, UserCheck, UserX } from "lucide-react";
import Modal from "../../components/ui/Modal";
import { Badge, Button, FormAlert, FormField } from "../../components/ui";
import { useToast } from "../../components/ui/Toast";
import { ErrorState } from "../../components/shared/State";
import { useAuth } from "../../auth/AuthContext";
import { useFetch } from "../../hooks/useFetch";
import { useSubmit } from "../../hooks/useSubmit";
import { formatDate } from "../../lib/format";
import { api } from "../../services/api";
import LinkBox from "./LinkBox";
import RoleCheckboxes from "./RoleCheckboxes";

/** Everything an administrator can do to one account. Each section only appears with the matching permission;
 *  the API enforces the same rules (e.g. you can't change your own roles or disable the last Super Administrator). */
export default function ManageUserDialog({ userId, roles, onClose, onChanged }) {
  const { user: me, can } = useAuth();
  const toast = useToast();
  const { data: user, error, refetch } = useFetch((s) => api.users.get(userId, s), [userId]);
  const employees = useFetch((s) => (can("employees:read") ? api.employees.list({ sort: "name" }, s) : Promise.resolve([])), []);
  const [details, setDetails] = useState(null);
  const [roleIds, setRoleIds] = useState(null);
  const [link, setLink] = useState(null);
  const [busy, setBusy] = useState(null);
  const isSelf = user?.id === me.id;

  const changed = (u) => { refetch(); onChanged(u); };
  const form = details ?? (user ? { full_name: user.full_name, employee_id: user.employee?.id ?? "" } : null);
  const selectedRoles = roleIds ?? user?.roles.map((r) => r.id) ?? [];

  const detailsSubmit = useSubmit(async () => {
    changed(await api.users.update(user.id, { full_name: form.full_name, employee_id: form.employee_id || null }));
    setDetails(null);
    toast.success("Account details saved.");
  });
  const rolesSubmit = useSubmit(async () => {
    changed(await api.users.setRoles(user.id, selectedRoles));
    setRoleIds(null);
    toast.success("Roles updated. They apply from the user's next click.");
  });

  async function act(name, fn, success) {
    setBusy(name);
    try {
      const result = await fn();
      if (success) toast.success(typeof success === "function" ? success(result) : success);
      return result;
    } catch (e) {
      toast.error(e.message);
      return null;
    } finally {
      setBusy(null);
    }
  }

  let body;
  if (error) body = <ErrorState error={error} onRetry={refetch} />;
  else if (!user) body = <div className="skeleton" style={{ height: 160 }} />;
  else body = (
    <div className="stack" style={{ gap: 22 }}>
      <dl className="dl" style={{ margin: 0 }}>
        <div><dt>Status</dt><dd>{user.status === "active" ? <Badge tone="success">Active</Badge> : <Badge tone="danger">Disabled</Badge>}</dd></div>
        <div><dt>Password</dt><dd>{user.has_password ? "Set" : <Badge tone="warning">Not set yet (invited)</Badge>}</dd></div>
        <div><dt>Signed in on</dt><dd>{user.active_sessions} browser{user.active_sessions === 1 ? "" : "s"}</dd></div>
        <div><dt>Last sign-in</dt><dd>{user.last_login_at ? formatDate(user.last_login_at) : "Never"}</dd></div>
      </dl>

      {can("users:manage") && (
        <form ref={detailsSubmit.formRef} onSubmit={detailsSubmit.submit} noValidate className="stack">
          <h3 className="section-title">Details</h3>
          <FormAlert>{detailsSubmit.formError && !Object.keys(detailsSubmit.errors).length ? detailsSubmit.formError : ""}</FormAlert>
          <div className="form-grid">
            <FormField label="Full name" required error={detailsSubmit.errors.full_name}>
              <input className="input" value={form.full_name} onChange={(e) => setDetails({ ...form, full_name: e.target.value })} maxLength={120} />
            </FormField>
            {can("employees:read") && (
              <FormField label="Linked employee record" error={detailsSubmit.errors.employee_id}>
                <select className="select" value={form.employee_id} onChange={(e) => setDetails({ ...form, employee_id: e.target.value })}>
                  <option value="">No linked employee</option>
                  {(employees.data ?? []).map((e) => <option key={e.id} value={e.id}>{e.full_name} ({e.employee_code})</option>)}
                </select>
              </FormField>
            )}
          </div>
          <div><Button type="submit" loading={detailsSubmit.pending} disabled={!details}>Save details</Button></div>
        </form>
      )}

      {can("roles:assign") && (
        <form ref={rolesSubmit.formRef} onSubmit={rolesSubmit.submit} noValidate className="stack">
          <h3 className="section-title">Roles</h3>
          {isSelf && <p className="muted">You can't change your own roles. Ask another administrator.</p>}
          <FormAlert>{rolesSubmit.formError ? (rolesSubmit.errors.role_ids || rolesSubmit.formError) : ""}</FormAlert>
          <RoleCheckboxes roles={roles} value={selectedRoles} onChange={setRoleIds} disabled={isSelf} idPrefix="user-role" />
          {!isSelf && <div><Button type="submit" loading={rolesSubmit.pending} disabled={!roleIds || !roleIds.length}>Save roles</Button></div>}
        </form>
      )}

      {can("users:manage") && (
        <div className="stack">
          <h3 className="section-title">Access</h3>
          <div className="page-actions">
            <Button icon={KeyRound} loading={busy === "link"}
              onClick={() => act("link", () => api.users.resetLink(user.id)).then((l) => l && setLink(l))}>Create password-reset link</Button>
            <Button icon={LogOut} loading={busy === "sessions"}
              onClick={() => act("sessions", () => api.users.revokeSessions(user.id), (r) => `Ended ${r.ended} session(s).`).then(() => refetch())}>
              End all sessions
            </Button>
            {!isSelf && (user.status === "active" ? (
              <Button variant="danger" icon={UserX} loading={busy === "status"}
                onClick={() => act("status", () => api.users.setStatus(user.id, "disabled"), `${user.full_name} was disabled and signed out.`).then((u) => u && changed(u))}>
                Disable account
              </Button>
            ) : (
              <Button icon={UserCheck} loading={busy === "status"}
                onClick={() => act("status", () => api.users.setStatus(user.id, "active"), `${user.full_name} was re-enabled.`).then((u) => u && changed(u))}>
                Re-enable account
              </Button>
            ))}
          </div>
          {link && <LinkBox link={link} label="Password-reset link" />}
        </div>
      )}
    </div>
  );

  return (
    <Modal size="wide" title={user ? user.full_name : "User"} description={user ? `${user.email} · ${user.id}` : undefined}
      onClose={onClose} footer={<Button onClick={onClose}>Close</Button>}>
      {body}
    </Modal>
  );
}
