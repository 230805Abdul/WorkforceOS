/** Simple horizontal bar chart. Values are printed as text, so it never relies on bar length or colour alone. */
export default function BarList({ items, tone }) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <ul className="bars">
      {items.map((i) => (
        <li key={i.label} className="bar-row">
          <span className="bar-label" title={i.label}>{i.label}</span>
          <span className="bar-track" aria-hidden="true"><span className={`bar-fill ${i.tone ?? tone ?? ""}`} style={{ width: `${(i.value / max) * 100}%` }} /></span>
          <span className="bar-val">{i.value}</span>
        </li>
      ))}
    </ul>
  );
}
