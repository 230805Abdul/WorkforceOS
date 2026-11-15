import { useState } from "react";
import { KeyRound, LogOut, UserRound } from "lucide-react";
import PageHeader from "../components/shared/PageHeader";
import PasswordInput from "../components/auth/PasswordInput";
import StatusBadge from "../components/shared/StatusBadge";
import { EmptyState, ErrorState } from "../components/shared/State";
import { Badge, Button, FormAlert, FormField } from "../components/ui";
import { useToast } from "../components/ui/Toast";
import { useAuth } from "../auth/AuthContext";
import { useFetch } from "../hooks/useFetch";
import { useSubmit } from "../hooks/useSubmit";
import { formatDate, formatDay } from "../lib/format";
import { api } from "../services/api";

function AccountCard() {
  const { user, updateUser, can } = useAuth();
  const toast = useToast();
  const [name, setName] = useState(user.full_name);
  const { submit, pending, errors, formError, formRef } = useSubmit(async () => {
    updateUser(await api.auth.updateProfile({ full_name: name }));
    toast.success("Your name was updated.");
  });
  return (
    <section className="card" aria-labelledby="h-account">
      <div className="card-head"><h2 id="h-account">Account</h2></div>
      <form className="card-body stack" ref={formRef} onSubmit={submit} noValidate>
        <FormAlert>{formError && !Object.keys(errors).length ? formError : ""}</FormAlert>
        <div className="form-grid">
          <FormField label="Full name" required error={errors.full_name}>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} disabled={!can("profile:own")} />
          </FormField>
          <FormField label="Email" hint="Ask an administrator to change your e-mail address.">
            <input className="input" value={user.email} readOnly />
          </FormField>
        </div>
        <dl className="dl" style={{ margin: 0 }}>
          <div><dt>Roles</dt><dd className="role-chips">{user.roles.map((r) => <Badge key={r.id} tone="accent">{r.label}</Badge>)}</dd></div>
          <div><dt>Last sign-in</dt><dd>{user.last_login_at ? formatDate(user.last_login_at) : "—"}</dd></div>
        </dl>
        {can("profile:own") && (
          <div><Button variant="primary" type="submit" loading={pending} disabled={name.trim() === user.full_name}>Save name</Button></div>
        )}
      </form>
    </section>
  );
}

function EmployeeRecordCard() {
  const { can } = useAuth();
  const toast = useToast();
  const { data, error, refetch } = useFetch((s) => api.me.employee(s), []);
  const [phone, setPhone] = useState(null);
  const { submit, pending, errors, formError, formRef } = useSubmit(async () => {
    await api.me.updateEmployee({ phone: phone ?? "" });
    toast.success("Your phone number was updated.");
    refetch();
  });
  if (!can("profile:own")) return null;
  let body;
  if (error?.code === "no_employee_record") {
    body = <EmptyState icon={UserRound} title="No employee record linked" message={error.message} />;
  } else if (error) {
    body = <ErrorState error={error} onRetry={refetch} />;
  } else if (!data) {
    body = <div className="skeleton" style={{ height: 80 }} />;
  } else {
    body = (
      <form className="stack" ref={formRef} onSubmit={submit} noValidate>
        <dl className="dl" style={{ margin: 0 }}>
          <div><dt>Name</dt><dd>{data.full_name}</dd></div>
          <div><dt>Employee code</dt><dd className="mono">{data.employee_code}</dd></div>
          <div><dt>Job title</dt><dd>{data.job_title}</dd></div>
          <div><dt>Department</dt><dd>{data.department}</dd></div>
          <div><dt>Status</dt><dd><StatusBadge status={data.employment_status} /></dd></div>
          <div><dt>Joined</dt><dd>{formatDay(data.joining_date)}</dd></div>
        </dl>
        <FormAlert>{formError && !Object.keys(errors).length ? formError : ""}</FormAlert>
        <FormField label="Phone" error={errors.phone} hint="The only detail you can change yourself. HR maintains the rest.">
          <input className="input" type="tel" value={phone ?? data.phone ?? ""} onChange={(e) => setPhone(e.target.value)} style={{ maxWidth: 280 }} />
        </FormField>
        <div><Button type="submit" loading={pending} disabled={phone === null}>Save phone</Button></div>
      </form>
    );
  }
  return (
    <section className="card" aria-labelledby="h-employee">
      <div className="card-head"><h2 id="h-employee">My employee record</h2></div>
      <div className="card-body">{body}</div>
    </section>
  );
}

function PasswordCard() {
  const { config } = useAuth();
  const toast = useToast();
  const empty = { current_password: "", new_password: "", new_password_confirm: "" };
  const [form, setForm] = useState(empty);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const { submit, pending, errors, formError, formRef } = useSubmit(async () => {
    await api.auth.changePassword(form);
    setForm(empty);
    toast.success("Password changed. Your other browsers were signed out.");
  });
  return (
    <section className="card" aria-labelledby="h-password">
      <div className="card-head"><h2 id="h-password">Change password</h2></div>
      <form className="card-body stack" ref={formRef} onSubmit={submit} noValidate>
        <FormAlert>{formError && !Object.keys(errors).length ? formError : ""}</FormAlert>
        <FormField label="Current password" required error={errors.current_password}>
          <PasswordInput value={form.current_password} onChange={set("current_password")} />
        </FormField>
        <div className="form-grid">
          <FormField label="New password" required error={errors.new_password} hint={config?.password_policy?.text}>
            <PasswordInput autoComplete="new-password" value={form.new_password} onChange={set("new_password")} />
          </FormField>
          <FormField label="Confirm new password" required error={errors.new_password_confirm}>
            <PasswordInput autoComplete="new-password" value={form.new_password_confirm} onChange={set("new_password_confirm")} />
          </FormField>
        </div>
        <div><Button variant="primary" icon={KeyRound} type="submit" loading={pending}>Change password</Button></div>
      </form>
    </section>
  );
}

function SessionsCard() {
  const { can } = useAuth();
  const toast = useToast();
  const [pending, setPending] = useState(false);
  if (!can("profile:own")) return null;
  async function endOthers() {
    setPending(true);
    try {
      const { ended } = await api.auth.logoutOthers();
      toast.success(ended ? `Signed out of ${ended} other browser${ended === 1 ? "" : "s"}.` : "You weren't signed in anywhere else.");
    } catch (e) {
      toast.error(e.message);
    } finally {
      setPending(false);
    }
  }
  return (
    <section className="card" aria-labelledby="h-sessions">
      <div className="card-head"><h2 id="h-sessions">Signed-in browsers</h2></div>
      <div className="card-body stack">
        <p className="muted">You can be signed in on up to 5 browsers at once. Signing in on a sixth ends the oldest session.
          Lost a device or used a shared computer? End every session except this one.</p>
        <div><Button icon={LogOut} onClick={endOthers} loading={pending}>Sign out other browsers</Button></div>
      </div>
    </section>
  );
}

function describeBrowser(ua) {
  if (!ua) return "Unknown browser";
  const browser = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : null;
  const os = /Windows/.test(ua) ? "Windows" : /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Mac OS/.test(ua) ? "macOS" : /Linux/.test(ua) ? "Linux" : null;
  return [browser, os].filter(Boolean).join(" on ") || ua.slice(0, 60);
}

function SignInsCard() {
  const { can } = useAuth();
  const { data, error, refetch } = useFetch((s) => (can("profile:own") ? api.auth.signIns(s) : Promise.resolve(null)), []);
  if (!can("profile:own")) return null;
  return (
    <section className="card" aria-labelledby="h-signins">
      <div className="card-head"><h2 id="h-signins">Recent sign-ins</h2></div>
      <div className="card-body stack">
        <p className="muted">Sign-ins to your account, newest first. Something you don't recognise? Change your password and
          sign out other browsers.</p>
        {error ? <ErrorState error={error} onRetry={refetch} /> : !data ? <div className="skeleton" /> : !data.length ? <p className="muted">No sign-ins recorded yet.</p> : (
          <ul className="mini-list">
            {data.map((s, i) => (
              <li key={i}>
                <div>
                  <strong>{s.outcome === "success" ? "Signed in" : s.reason === "account_disabled" ? "Refused: account disabled" : "Failed attempt (wrong password)"}</strong>
                  <span className="cell-sub">{formatDate(s.at)} {new Date(s.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} · {describeBrowser(s.user_agent)} · {s.ip ?? "unknown address"}</span>
                </div>
                {s.new_device ? <Badge tone="warning">New device</Badge> : s.outcome !== "success" ? <Badge tone="danger">Failed</Badge> : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

export default function Profile() {
  return (
    <>
      <PageHeader title="My profile" description="Your account, your employee record and your password." />
      <div className="grid-2" style={{ alignItems: "start" }}>
        <div className="stack"><AccountCard /><EmployeeRecordCard /></div>
        <div className="stack"><PasswordCard /><SessionsCard /><SignInsCard /></div>
      </div>
    </>
  );
}
