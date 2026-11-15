import { useState } from "react";
import { Building2, Pencil, Plus, Trash2 } from "lucide-react";
import { api } from "../services/api";
import { useFetch } from "../hooks/useFetch";
import { useDebounce } from "../hooks/useDebounce";
import PageHeader from "../components/shared/PageHeader";
import FilterBar from "../components/shared/FilterBar";
import DataTable from "../components/shared/DataTable";
import ConfirmDialog from "../components/shared/ConfirmDialog";
import SampleTag from "../components/shared/SampleTag";
import { EmptyState } from "../components/shared/State";
import { Button, IconButton } from "../components/ui";
import Modal from "../components/ui/Modal";
import { useToast } from "../components/ui/Toast";
import DepartmentFormDialog from "../features/departments/DepartmentFormDialog";
import DepartmentDetailDialog from "../features/departments/DepartmentDetailDialog";
import { useAuth } from "../auth/AuthContext";

export default function Departments() {
  const { can } = useAuth();
  const toast = useToast();
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("name");
  const [order, setOrder] = useState("asc");
  const [dialog, setDialog] = useState(null); // { type: 'create'|'edit'|'view'|'delete', department? }
  const search = useDebounce(query);

  const { data, error, loading, refetch } = useFetch((s) => api.departments.list({ search, sort, order }, s), [search, sort, order]);

  const onSort = (key) => {
    if (key === sort) setOrder(order === "asc" ? "desc" : "asc");
    else { setSort(key); setOrder(key.endsWith("_count") ? "desc" : "asc"); }
  };
  const close = () => setDialog(null);

  async function remove(d) {
    try {
      await api.departments.remove(d.id);
      toast.success(`“${d.name}” was deleted.`);
      refetch();
    } catch (e) {
      toast.error(e.message); // e.g. "Cannot delete 'Engineering': it still has 4 employees and 2 jobs."
    }
    close();
  }

  const columns = [
    { key: "name", header: "Department", sortable: true, render: (d) => (
      <><button type="button" className="link-btn" onClick={() => setDialog({ type: "view", department: d })}>{d.name}</button>
        <SampleTag show={d.is_sample} />
        <div className="cell-sub">{d.description || d.id}</div></>
    ) },
    { key: "code", header: "Code", sortable: true, render: (d) => <span className="mono">{d.code}</span> },
    { key: "employees_count", header: "Employees", sortable: true, align: "right",
      render: (d) => <span className="mono" title={`${d.active_employees_count} active`}>{d.employees_count}</span> },
    { key: "jobs_count", header: "Jobs", sortable: true, align: "right", render: (d) => <span className="mono">{d.jobs_count}</span> },
    { key: "actions", header: <span className="sr-only">Actions</span>, render: (d) => (
      <div className="cell-actions">
        {can("departments:manage") && <IconButton icon={Pencil} label={`Edit ${d.name}`} onClick={() => setDialog({ type: "edit", department: d })} />}
        {can("departments:manage") && <IconButton icon={Trash2} danger label={`Delete ${d.name}`} onClick={() => setDialog({ type: "delete", department: d })} />}
      </div>
    ) },
  ];

  const empty = query ? (
    <EmptyState title="No departments match your search" action={<Button onClick={() => setQuery("")}>Clear search</Button>} />
  ) : (
    <EmptyState icon={Building2} title="No departments yet" message="Create a department before adding employees or jobs."
      action={can("departments:manage") && <Button variant="primary" icon={Plus} onClick={() => setDialog({ type: "create" })}>New department</Button>} />
  );

  const inUse = dialog?.type === "delete" && (dialog.department.employees_count > 0 || dialog.department.jobs_count > 0);

  return (
    <>
      <PageHeader title="Departments" description="How your organisation is structured. Employees and jobs each belong to one department."
        actions={can("departments:manage") && <Button variant="primary" icon={Plus} onClick={() => setDialog({ type: "create" })}>New department</Button>} />
      <div className="card">
        <FilterBar search={query} onSearch={setQuery} placeholder="Search name or code…" searchLabel="Search departments"
          active={!!query} onClear={() => setQuery("")} count={data?.length} noun="department" />
        <DataTable caption="Departments" columns={columns} rows={data} loading={loading} error={error} onRetry={refetch}
          sort={sort} order={order} onSort={onSort} empty={empty} />
      </div>

      {(dialog?.type === "create" || dialog?.type === "edit") && (
        <DepartmentFormDialog department={dialog.department} onClose={close} onSaved={() => { close(); refetch(); }} />
      )}
      {dialog?.type === "view" && (
        <DepartmentDetailDialog department={dialog.department} onClose={close} onEdit={(department) => setDialog({ type: "edit", department })} />
      )}
      {dialog?.type === "delete" && (inUse ? (
        <Modal size="narrow" title="This department is still in use" onClose={close}
          footer={<><Button onClick={close}>Close</Button>
            <Button variant="primary" onClick={() => setDialog({ type: "view", department: dialog.department })}>View department</Button></>}>
          <p><strong>{dialog.department.name}</strong> has {dialog.department.employees_count} employee(s) and {dialog.department.jobs_count} job(s).
            Move them to another department or delete them first. The database also enforces this rule (ON DELETE RESTRICT).</p>
        </Modal>
      ) : (
        <ConfirmDialog title="Delete this department?" onConfirm={() => remove(dialog.department)} onClose={close}>
          <p><strong>{dialog.department.name}</strong> has no employees or jobs and will be removed permanently.</p>
        </ConfirmDialog>
      ))}
    </>
  );
}
