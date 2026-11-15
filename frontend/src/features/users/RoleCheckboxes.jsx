/** Checkbox list of roles. `value` is an array of role ids. */
export default function RoleCheckboxes({ roles, value, onChange, disabled, idPrefix = "role" }) {
  const toggle = (id) => onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);
  return (
    <div className="stack" style={{ gap: 4 }} role="group" aria-label="Roles">
      {roles.map((r) => (
        <label key={r.id} className="perm-row" htmlFor={`${idPrefix}-${r.id}`}>
          <input id={`${idPrefix}-${r.id}`} type="checkbox" checked={value.includes(r.id)} disabled={disabled} onChange={() => toggle(r.id)} />
          <span><strong>{r.label}</strong><br /><span className="cell-sub">{r.description}</span></span>
        </label>
      ))}
    </div>
  );
}
