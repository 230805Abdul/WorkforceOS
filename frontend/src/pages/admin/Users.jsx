import { useState } from "react";
import { UserPlus, Users as UsersIcon } from "lucide-react";
import { api } from "../../services/api";
import { useFetch } from "../../hooks/useFetch";
import { useDebounce } from "../../hooks/useDebounce";
import { useAuth } from "../../auth/AuthContext";
import PageHeader from "../../components/shared/PageHeader";
import FilterBar from "../../components/shared/FilterBar";
import DataTable from "../../components/shared/DataTable";
import SampleTag from "../../components/shared/SampleTag";
import { EmptyState } from "../../components/shared/State";
import { Badge, Button } from "../../components/ui";
import InviteUserDialog from "../../features/users/InviteUserDialog";
import ManageUserDialog from "../../features/users/ManageUserDialog";
import { formatDate, initials } from "../../lib/format";

const NO_FILTERS = { search: "", status: "", role: "" };

export default function Users() {
  const { can, user: me } = useAuth();
  const [f, setF] = useState(NO_FILTERS);
  const [dialog, setDialog] = useState(null); // "invite" | { manage: userId }
  const search = useDebounce(f.search);
  const roles = useFetch((s) => api.roles.list(s), []);
  const { data, error, loading, refetch } = useFetch((s) => api.users.list({ search, status: f.status, role: f.role }, s), [search, f.status, f.role]);
  const active = f.search || f.status || f.role;

  const columns = [
    { key: "full_name", header: "User", render: (u) => (
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <span className="avatar" aria-hidden="true">{initials(u.full_name)}</span>
        <div>
          <button type="button" className="link-btn" onClick={() => setDialog({ manage: u.id })}>{u.full_name}</button>
          {u.id === me.id && <span className="cell-sub"> (you)</span>}<SampleTag show={u.is_sample} />
          <div className="cell-sub">{u.email}</div>
        </div>
      </div>
    ) },
    { key: "roles", header: "Roles", render: (u) => <div className="role-chips">{u.roles.map((r) => <Badge key={r.id} tone="accent">{r.label}</Badge>)}</div> },
    { key: "status", header: "Status", render: (u) => u.status === "active"
      ? (u.has_password ? <Badge tone="success">Active</Badge> : <Badge tone="warning">Invited</Badge>)
      : <Badge tone="danger">Disabled</Badge> },
    { key: "employee", header: "Employee record", render: (u) => u.employee ? `${u.employee.full_name} (${u.employee.employee_code})` : <span className="muted">—</span> },
    { key: "last_login_at", header: "Last sign-in", render: (u) => (u.last_login_at ? formatDate(u.last_login_at) : <span className="muted">Never</span>) },
  ];

  return (
    <>
      <PageHeader title="Users" description="Who can sign in to WorkforceOS, and with which roles. Accounts are separate from employee records but can be linked to one."
        actions={can("users:manage") && <Button variant="primary" icon={UserPlus} onClick={() => setDialog("invite")} disabled={!roles.data}>Invite user</Button>} />
      <div className="card">
        <FilterBar search={f.search} onSearch={(v) => setF({ ...f, search: v })} placeholder="Search name or email…" searchLabel="Search users"
          active={!!active} onClear={() => setF(NO_FILTERS)} count={data?.length} noun="user">
          <select className="select" aria-label="Filter by status" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
            <option value="">All statuses</option><option value="active">Active</option><option value="disabled">Disabled</option>
          </select>
          <select className="select" aria-label="Filter by role" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>
            <option value="">All roles</option>
            {(roles.data ?? []).map((r) => <option key={r.id} value={r.name}>{r.label}</option>)}
          </select>
        </FilterBar>
        <DataTable caption="Users" columns={columns} rows={data} loading={loading} error={error} onRetry={refetch}
          empty={<EmptyState icon={UsersIcon} title={active ? "No users match your filters" : "No users"} />} />
      </div>
      {dialog === "invite" && <InviteUserDialog roles={roles.data} onClose={() => setDialog(null)} onSaved={refetch} />}
      {dialog?.manage && <ManageUserDialog userId={dialog.manage} roles={roles.data ?? []} onClose={() => setDialog(null)} onChanged={refetch} />}
    </>
  );
}
