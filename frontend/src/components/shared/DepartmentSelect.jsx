/** <select> of real departments. Pass the result of useDepartments(). Extra props go to the <select>. */
export default function DepartmentSelect({ departments, placeholder, ...rest }) {
  const list = departments.data ?? [];
  return (
    <select className="select" disabled={!departments.data && !departments.error} {...rest}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {departments.error && <option value="" disabled>Could not load departments</option>}
      {list.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
    </select>
  );
}
