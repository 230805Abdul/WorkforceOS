import { Search, X } from "lucide-react";
import { Button } from "../ui";

/** Search box + filter controls (children) + "Clear filters" + result count. */
export default function FilterBar({ search, onSearch, placeholder, searchLabel, active, onClear, count, noun, children }) {
  return (
    <div className="toolbar" role="search">
      <div className="search">
        <Search size={16} aria-hidden="true" />
        <input className="input" type="search" value={search} onChange={(e) => onSearch(e.target.value)} placeholder={placeholder} aria-label={searchLabel} />
      </div>
      {children}
      {active && <Button variant="ghost" size="sm" icon={X} onClick={onClear}>Clear filters</Button>}
      {count !== undefined && <span className="toolbar-count" aria-live="polite">{count} {noun}{count === 1 ? "" : "s"}</span>}
    </div>
  );
}
