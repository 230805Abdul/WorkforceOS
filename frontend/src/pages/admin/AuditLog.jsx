import { Fragment, useEffect, useState } from "react";
import { AlertTriangle, ChevronDown, ChevronRight, KeyRound, LogIn, ShieldAlert, ShieldCheck, Timer, UserX } from "lucide-react";
import { api } from "../../services/api";
import { useDebounce } from "../../hooks/useDebounce";
import { useFetch } from "../../hooks/useFetch";
import PageHeader from "../../components/shared/PageHeader";
import FilterBar from "../../components/shared/FilterBar";
import { EmptyState, ErrorState } from "../../components/shared/State";
import { Badge, Button, IconButton } from "../../components/ui";

const CATEGORIES = ["auth", "user", "role", "employee", "department", "job", "candidate", "application", "system", "security"];
const OUTCOME_TONE = { success: "success", failure: "warning", denied: "danger" };
const NO_FILTERS = { search: "", category: "", outcome: "" };

const when = (iso) => new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" });

function Stat({ icon: Icon, value, label, tone }) {
  return (
    <div className="card kpi">
      <span className={`kpi-icon ${tone ?? ""}`}><Icon size={19} aria-hidden="true" /></span>
      <div><div className="kpi-value">{value}</div><div className="kpi-label">{label}</div></div>
    </div>
  );
}

function Summary() {
  const { data, error } = useFetch((s) => api.audit.summary(s), []);
  if (error || !data) return null;
  return (
    <>
      <h2 className="kpis-section-title">Last 24 hours</h2>
      <div className="kpis">
        <Stat icon={LogIn} value={data.successful_sign_ins} label="Sign-ins" />
        <Stat icon={UserX} value={data.failed_sign_ins} label="Failed sign-ins" tone={data.failed_sign_ins ? "warn" : ""} />
        <Stat icon={ShieldAlert} value={data.access_denied + data.cross_site_refused} label="Refused requests" tone={data.access_denied ? "warn" : ""} />
        <Stat icon={Timer} value={data.rate_limited} label="Rate-limit blocks" />
        <Stat icon={KeyRound} value={data.new_device_sign_ins} label="New-device sign-ins" />
      </div>
      {data.most_failed_emails.length > 0 && (
        <p className="muted" style={{ marginBottom: 16 }}>
          Most failed sign-ins: {data.most_failed_emails.map((e) => `${e.email} (${e.failures})`).join(", ")}
        </p>
      )}
    </>
  );
}

function IntegrityCheck() {
  const [state, setState] = useState(null);
  async function run() {
    setState({ running: true });
    try {
      setState({ result: await api.audit.verify() });
    } catch (e) {
      setState({ error: e.message });
    }
  }
  const r = state?.result;
  return (
    <div className="stack" style={{ gap: 8, marginBottom: 16 }}>
      <div><Button icon={ShieldCheck} onClick={run} loading={state?.running}>Verify integrity</Button></div>
      {state?.error && <div className="form-alert" role="alert">{state.error}</div>}
      {r && (r.ok ? (
        <div className="auth-notice" role="status" style={{ marginTop: 0 }}>
          <ShieldCheck size={16} aria-hidden="true" />
          <span>Intact: all {r.checked} records match their signatures and none is missing from the chain.
            {r.development_key && " (Signed with the development key: set AUDIT_HMAC_KEY for real protection.)"}</span>
        </div>
      ) : (
        <div className="form-alert" role="alert"><AlertTriangle size={16} aria-hidden="true" />
          <span><strong>Integrity problem</strong>{r.first_problem_id ? ` at record #${r.first_problem_id}` : ""}: {r.problem}</span></div>
      ))}
    </div>
  );
}

export default function AuditLog() {
  const [f, setF] = useState(NO_FILTERS);
  const search = useDebounce(f.search);
  const [pages, setPages] = useState({ items: [], next: null, loadingMore: false });
  const [open, setOpen] = useState(() => new Set());
  const params = { search, category: f.category, outcome: f.outcome, limit: 50 };
  const first = useFetch((s) => api.audit.events(params, s), [search, f.category, f.outcome]);

  useEffect(() => {
    if (first.data) setPages({ items: first.data.items, next: first.data.next_before_id, loadingMore: false });
  }, [first.data]);

  async function loadMore() {
    setPages((p) => ({ ...p, loadingMore: true }));
    try {
      const more = await api.audit.events({ ...params, before_id: pages.next });
      setPages((p) => ({ items: [...p.items, ...more.items], next: more.next_before_id, loadingMore: false }));
    } catch {
      setPages((p) => ({ ...p, loadingMore: false }));
    }
  }
  const toggle = (id) => setOpen((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const active = f.search || f.category || f.outcome;

  let table;
  if (first.error && !first.data) table = <ErrorState error={first.error} onRetry={first.refetch} />;
  else if (!first.data) table = <div className="card-body"><div className="skeleton" style={{ height: 120 }} /></div>;
  else if (!pages.items.length) table = <EmptyState icon={ShieldCheck} title={active ? "No records match your filters" : "No audit records yet"} />;
  else table = (
    <>
      <div className={`table-wrap ${first.loading ? "refreshing" : ""}`} tabIndex={0} role="region" aria-label="Audit records">
        <table className="table">
          <caption className="sr-only">Audit records, newest first</caption>
          <thead><tr>
            <th scope="col"><span className="sr-only">Details</span></th><th scope="col">When</th><th scope="col">Action</th>
            <th scope="col">Outcome</th><th scope="col">Who</th><th scope="col">Target</th><th scope="col">From</th>
          </tr></thead>
          <tbody>
            {pages.items.map((e) => (
              <Fragment key={e.id}>
                <tr>
                  <td style={{ width: 44 }}>
                    <IconButton icon={open.has(e.id) ? ChevronDown : ChevronRight} label={`${open.has(e.id) ? "Hide" : "Show"} details of record ${e.id}`}
                      onClick={() => toggle(e.id)} aria-expanded={open.has(e.id)} />
                  </td>
                  <td className="mono" style={{ whiteSpace: "nowrap" }}>{when(e.occurred_at)}</td>
                  <td><code>{e.action}</code><div className="cell-sub">{e.category}</div></td>
                  <td><Badge tone={OUTCOME_TONE[e.outcome]}>{e.outcome}</Badge></td>
                  <td>{e.actor_email ?? <span className="muted">{e.details.email ? `(tried ${e.details.email})` : "—"}</span>}</td>
                  <td>{e.target_id ? <span className="mono">{e.target_id}</span> : <span className="muted">—</span>}</td>
                  <td className="mono">{e.ip ?? "—"}</td>
                </tr>
                {open.has(e.id) && (
                  <tr>
                    <td />
                    <td colSpan={6}>
                      <dl className="dl" style={{ margin: 0 }}>
                        <div><dt>Record</dt><dd className="mono">#{e.id}</dd></div>
                        <div><dt>Request reference</dt><dd className="mono">{e.request_id ?? "—"}</dd></div>
                        <div className="span-2"><dt>Browser</dt><dd>{e.user_agent ?? "—"}</dd></div>
                        <div className="span-2"><dt>Details</dt><dd><pre className="audit-details">{JSON.stringify(e.details, null, 2)}</pre></dd></div>
                      </dl>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pager">
        <span>{pages.items.length} record{pages.items.length === 1 ? "" : "s"} shown</span>
        {pages.next && <Button size="sm" onClick={loadMore} loading={pages.loadingMore}>Load older records</Button>}
      </div>
    </>
  );

  return (
    <>
      <PageHeader title="Audit log" description="An append-only record of sign-ins, account and data changes, and refused or suspicious requests. The app and its database account can only add records; the integrity check reveals most later edits, but not changes made by someone holding both database-owner access and the signing key." />
      <Summary />
      <IntegrityCheck />
      <div className="card">
        <FilterBar search={f.search} onSearch={(v) => setF({ ...f, search: v })} placeholder="Search action, e-mail, ID, IP, reference…"
          searchLabel="Search audit log" active={!!active} onClear={() => setF(NO_FILTERS)}>
          <select className="select" aria-label="Filter by category" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
            <option value="">All categories</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select className="select" aria-label="Filter by outcome" value={f.outcome} onChange={(e) => setF({ ...f, outcome: e.target.value })}>
            <option value="">All outcomes</option><option value="success">Success</option><option value="failure">Failure</option><option value="denied">Denied</option>
          </select>
        </FilterBar>
        {table}
      </div>
    </>
  );
}
