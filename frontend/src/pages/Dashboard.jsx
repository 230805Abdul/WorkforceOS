import { useState } from "react";
import { Link } from "react-router-dom";
import { Activity, Briefcase, Building2, CheckCircle2, FileText, GitPullRequestArrow, KeyRound, Plus, UserCheck, UserCog, UserPlus, UserRound, Users } from "lucide-react";
import { api } from "../services/api";
import { useFetch } from "../hooks/useFetch";
import PageHeader from "../components/shared/PageHeader";
import BarList from "../components/shared/BarList";
import StatusBadge from "../components/shared/StatusBadge";
import { EmptyState, ErrorState } from "../components/shared/State";
import { Button } from "../components/ui";
import JobFormDialog from "../features/jobs/JobFormDialog";
import CandidateFormDialog from "../features/candidates/CandidateFormDialog";
import EmployeeFormDialog from "../features/employees/EmployeeFormDialog";
import { SOURCE_LABELS, STATUS_LABELS, timeAgo } from "../lib/format";
import { useAuth } from "../auth/AuthContext";

const KINDS = { job: Briefcase, candidate: Users, application: FileText, employee: UserRound, department: Building2, user: UserCog, role: KeyRound };

function Kpi({ icon: Icon, value, label, hint }) {
  return (
    <div className="card kpi">
      <span className="kpi-icon"><Icon size={19} aria-hidden="true" /></span>
      <div>
        <div className="kpi-value">{value}</div>
        <div className="kpi-label">{label}</div>
        <div className="kpi-hint">{hint}</div>
      </div>
    </div>
  );
}

function Workforce({ data }) {
  const { kpis, employees_by_department: byDept, employment_status: empStatus } = data;
  return (
    <>
      <h2 className="kpis-section-title">Workforce</h2>
      <div className="kpis">
        <Kpi icon={UserRound} value={kpis.total_employees} label="Employees" hint="All employee records" />
        <Kpi icon={UserCheck} value={kpis.active_employees} label="Active employees"
          hint={`${kpis.total_employees - kpis.active_employees} on leave or terminated`} />
        <Kpi icon={Building2} value={kpis.total_departments} label="Departments" hint="In your organisation" />
      </div>
      <div className="grid-2">
        <section className="card" aria-labelledby="h-emp-dept">
          <div className="card-head"><h2 id="h-emp-dept">Employees by department</h2><Link to="/employees">View employees</Link></div>
          <div className="card-body">
            {byDept.length ? <BarList items={byDept.map((d) => ({ label: d.department, value: d.count }))} />
              : <EmptyState title="No current employees" message="Add employees to see how they are distributed." />}
            <p className="muted" style={{ marginTop: 10, fontSize: 12 }}>Active and on-leave employees; terminated records are not counted.</p>
          </div>
        </section>
        <section className="card" aria-labelledby="h-emp-status">
          <div className="card-head"><h2 id="h-emp-status">Employment status</h2></div>
          <div className="card-body">
            <BarList items={empStatus.map((e) => ({ label: STATUS_LABELS[e.status], value: e.count,
              tone: e.status === "active" ? "success" : e.status === "terminated" ? "danger" : "" }))} />
          </div>
        </section>
      </div>
    </>
  );
}

function Recruiting({ data }) {
  const { kpis, pipeline, departments } = data;
  return (
    <>
      <h2 className="kpis-section-title">Recruiting</h2>
      <div className="kpis">
        <Kpi icon={Briefcase} value={kpis.open_roles} label="Open roles" hint={`${kpis.open_positions} positions to fill`} />
        <Kpi icon={Users} value={kpis.total_candidates} label="Candidates" hint="In your talent pool" />
        <Kpi icon={GitPullRequestArrow} value={kpis.active_applications} label="Active applications"
          hint={`${kpis.offers_pending} offer${kpis.offers_pending === 1 ? "" : "s"} pending`} />
        <Kpi icon={CheckCircle2} value={kpis.hired} label="Hires" hint="Across all roles" />
      </div>
      <div className="grid-2">
        <section className="card" aria-labelledby="h-pipeline">
          <div className="card-head"><h2 id="h-pipeline">Hiring pipeline</h2><Link to="/pipeline">View board</Link></div>
          <div className="card-body">
            <BarList items={pipeline.map((p) => ({ label: STATUS_LABELS[p.status], value: p.count,
              tone: p.status === "hired" ? "success" : p.status === "rejected" ? "danger" : "" }))} />
          </div>
        </section>
        <section className="card" aria-labelledby="h-dept">
          <div className="card-head"><h2 id="h-dept">Open roles by department</h2><Link to="/jobs">View jobs</Link></div>
          <div className="card-body">
            {departments.length ? <BarList items={departments.map((d) => ({ label: d.department, value: d.open_roles }))} />
              : <EmptyState title="No open roles" message="Publish a job to see it here." />}
          </div>
        </section>
      </div>
    </>
  );
}

function RecentApplications({ recent }) {
  return (
    <section className="card" aria-labelledby="h-recent">
      <div className="card-head"><h2 id="h-recent">Recent applications</h2><Link to="/pipeline">View all</Link></div>
      <div className="card-body">
        {recent.length ? (
          <ul className="mini-list">
            {recent.map((a) => (
              <li key={a.id}>
                <div><strong>{a.candidate_name}</strong><span className="cell-sub">{a.job_title} · {timeAgo(a.created_at)}</span></div>
                <StatusBadge status={a.status} />
              </li>
            ))}
          </ul>
        ) : <EmptyState title="No applications yet" message="Add a candidate and attach them to an open job." />}
      </div>
    </section>
  );
}

function Sources({ sources }) {
  return (
    <section className="card" aria-labelledby="h-src">
      <div className="card-head"><h2 id="h-src">Candidate sources</h2></div>
      <div className="card-body">
        {sources.length ? <BarList items={sources.map((s) => ({ label: SOURCE_LABELS[s.source], value: s.count }))} /> : <p className="muted">No candidates yet.</p>}
      </div>
    </section>
  );
}

function ActivityFeed({ activity }) {
  return (
    <section className="card" aria-labelledby="h-act">
      <div className="card-head"><h2 id="h-act">Recent activity</h2></div>
      <div className="card-body">
        {activity.length ? (
          <ul className="feed">
            {activity.map((a) => {
              const Icon = KINDS[a.kind] ?? Activity;
              return (
                <li key={a.id}>
                  <span className="feed-dot"><Icon size={14} aria-hidden="true" /></span>
                  <div><p>{a.message}</p><time dateTime={a.at}>{timeAgo(a.at)}</time></div>
                </li>
              );
            })}
          </ul>
        ) : <p className="muted">Nothing you can see has happened yet.</p>}
      </div>
    </section>
  );
}

/** Each section appears only if the SERVER sent it: the API leaves out what your role may not see. */
export default function Dashboard() {
  const { can } = useAuth();
  const { data, error, refetch } = useFetch((s) => api.dashboard(s), []);
  const [dialog, setDialog] = useState(null);
  const saved = () => { setDialog(null); refetch(); };

  const actions = (
    <>
      {can("employees:create") && can("departments:read") && <Button icon={UserRound} onClick={() => setDialog("employee")}>Add employee</Button>}
      {can("candidates:manage") && <Button icon={UserPlus} onClick={() => setDialog("candidate")}>Add candidate</Button>}
      {can("jobs:manage") && can("departments:read") && <Button variant="primary" icon={Plus} onClick={() => setDialog("job")}>New job</Button>}
    </>
  );

  let body;
  if (error && !data) body = <div className="card"><ErrorState error={error} onRetry={refetch} /></div>;
  else if (!data) body = <div className="kpis">{[0, 1, 2, 3].map((i) => <div key={i} className="card kpi" role="status" aria-label="Loading"><div className="skeleton" style={{ width: "100%", height: 56 }} /></div>)}</div>;
  else {
    const rec = data.recruiting;
    body = (
      <>
        {data.workforce && <Workforce data={data.workforce} />}
        {rec && <Recruiting data={rec} />}
        <div className={rec ? "grid-3" : ""}>
          {rec && <RecentApplications recent={rec.recent_applications} />}
          <div style={{ display: "grid", gap: 16, alignContent: "start" }}>
            {rec && <Sources sources={rec.sources} />}
            <ActivityFeed activity={data.activity} />
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <PageHeader title="Dashboard" description="A live view of your workforce and hiring. Every number is calculated by the database; you see the sections your role allows." actions={actions} />
      {body}
      {dialog === "job" && <JobFormDialog onClose={() => setDialog(null)} onSaved={saved} />}
      {dialog === "employee" && <EmployeeFormDialog onClose={() => setDialog(null)} onSaved={saved} />}
      {dialog === "candidate" && <CandidateFormDialog onClose={() => setDialog(null)} onSaved={saved} />}
    </>
  );
}
