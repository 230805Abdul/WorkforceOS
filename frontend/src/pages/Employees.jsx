import { useState } from "react";
import { Pencil, Plus, Trash2, UserRound } from "lucide-react";
import { api } from "../services/api";
import { useFetch } from "../hooks/useFetch";
import { useDebounce } from "../hooks/useDebounce";
import { useDepartments } from "../hooks/useDepartments";
import { useMeta } from "../lib/MetaContext";
import PageHeader from "../components/shared/PageHeader";
import FilterBar from "../components/shared/FilterBar";
import DataTable from "../components/shared/DataTable";
import StatusBadge from "../components/shared/StatusBadge";
import ConfirmDialog from "../components/shared/ConfirmDialog";
import DepartmentSelect from "../components/shared/DepartmentSelect";
import SampleTag from "../components/shared/SampleTag";
import { EmptyState } from "../components/shared/State";
import { Button, IconButton } from "../components/ui";
import { useToast } from "../components/ui/Toast";
import EmployeeFormDialog from "../features/employees/EmployeeFormDialog";
import EmployeeDetailDialog from "../features/employees/EmployeeDetailDialog";
import { STATUS_LABELS, formatDay, initials } from "../lib/format";
import { useAuth } from "../auth/AuthContext";

const NO_FILTERS = { search: "", employment_status: "", department_id: "" };

export default function Employees() {
  const { can } = useAuth();
  const meta = useMeta();
  const toast = useToast();
  const departments = useDepartments();
  const [f, setF] = useState(NO_FILTERS);
  const [sort, setSort] = useState("name");
  const [order, setOrder] = useState("asc");
  const [dialog, setDialog] = useState(null); // { type: 'create'|'edit'|'view'|'delete', employee? }
  const search = useDebounce(f.search);

  const { data, error, loading, refetch } = useFetch(
    (s) => api.employees.list({ search, employment_status: f.employment_status, department_id: f.department_id, sort, order }, s),
    [search, f.employment_status, f.department_id, sort, order]
  );

  const onSort = (key) => {
    if (key === sort) setOrder(order === "asc" ? "desc" : "asc");
    else { setSort(key); setOrder(key === "joining_date" ? "desc" : "asc"); }
  };
  const close = () => setDialog(null);
  const filtersActive = f.search || f.employment_status || f.department_id;

  async function remove(e) {
    try {
      await api.employees.remove(e.id);
      toast.success(`${e.full_name}'s record was deleted.`);
      refetch();
    } catch (err) {
      toast.error(err.message);
    }
    close();
  }

  const columns = [
    { key: "name", header: "Employee", sortable: true, render: (e) => (
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <span className="avatar" aria-hidden="true">{initials(e.full_name)}</span>
        <div>
          <button type="button" className="link-btn" onClick={() => setDialog({ type: "view", employee: e })}>{e.full_name}</button>
          <SampleTag show={e.is_sample} />
          <div className="cell-sub">{e.email}</div>
        </div>
      </div>
    ) },
    { key: "employee_code", header: "Code", sortable: true, render: (e) => <span className="mono">{e.employee_code}</span> },
    { key: "job_title", header: "Job title", sortable: true },
    { key: "department", header: "Department", sortable: true },
    { key: "employment_status", header: "Status", sortable: true, render: (e) => <StatusBadge status={e.employment_status} /> },
    { key: "joining_date", header: "Joined", sortable: true, render: (e) => formatDay(e.joining_date) },
    { key: "actions", header: <span className="sr-only">Actions</span>, render: (e) => (
      <div className="cell-actions">
        {can("employees:update") && <IconButton icon={Pencil} label={`Edit ${e.full_name}`} onClick={() => setDialog({ type: "edit", employee: e })} />}
        {can("employees:delete") && <IconButton icon={Trash2} danger label={`Delete ${e.full_name}`} onClick={() => setDialog({ type: "delete", employee: e })} />}
      </div>
    ) },
  ];

  const empty = filtersActive ? (
    <EmptyState title="No employees match your filters" message="Try a different search term or clear the filters."
      action={<Button onClick={() => setF(NO_FILTERS)}>Clear filters</Button>} />
  ) : (
    <EmptyState icon={UserRound} title="No employees yet" message="Add your first employee, or create one from a hired candidate on the Pipeline page."
      action={can("employees:create") && <Button variant="primary" icon={Plus} onClick={() => setDialog({ type: "create" })}>Add employee</Button>} />
  );

  return (
    <>
      <PageHeader title="Employees" description="Everyone who works here, with their department and employment status."
        actions={can("employees:create") && <Button variant="primary" icon={Plus} onClick={() => setDialog({ type: "create" })}>Add employee</Button>} />
      <div className="card">
        <FilterBar search={f.search} onSearch={(v) => setF({ ...f, search: v })} placeholder="Search name, email, code, title…"
          searchLabel="Search employees" active={!!filtersActive} onClear={() => setF(NO_FILTERS)} count={data?.length} noun="employee">
          <select className="select" aria-label="Filter by status" value={f.employment_status} onChange={(e) => setF({ ...f, employment_status: e.target.value })}>
            <option value="">All statuses</option>
            {meta.employment_statuses.map((s) => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
          </select>
          <DepartmentSelect departments={departments} aria-label="Filter by department" placeholder="All departments"
            value={f.department_id} onChange={(e) => setF({ ...f, department_id: e.target.value })} />
        </FilterBar>
        <DataTable caption="Employees" columns={columns} rows={data} loading={loading} error={error} onRetry={refetch}
          sort={sort} order={order} onSort={onSort} empty={empty} />
      </div>

      {(dialog?.type === "create" || dialog?.type === "edit") && (
        <EmployeeFormDialog employee={dialog.employee} onClose={close} onSaved={() => { close(); refetch(); }} />
      )}
      {dialog?.type === "view" && (
        <EmployeeDetailDialog employee={dialog.employee} onClose={close} onEdit={(employee) => setDialog({ type: "edit", employee })} />
      )}
      {dialog?.type === "delete" && (
        <ConfirmDialog title="Delete this employee record?" onConfirm={() => remove(dialog.employee)} onClose={close}>
          <p><strong>{dialog.employee.full_name}</strong> ({dialog.employee.employee_code}) will be removed permanently.</p>
          <p style={{ marginTop: 8 }}>If they left the company, consider setting their status to <strong>Terminated</strong> instead, so the history is kept.</p>
        </ConfirmDialog>
      )}
    </>
  );
}
