import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Info } from "lucide-react";
import AuthLayout from "../../components/auth/AuthLayout";
import PasswordInput from "../../components/auth/PasswordInput";
import { Button, FormAlert, FormField } from "../../components/ui";
import { useAuth } from "../../auth/AuthContext";
import { useSubmit } from "../../hooks/useSubmit";

/** Only allow redirects to our own pages (never to another site: "open redirect"). */
export function safeNext(next) {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/";
}

export default function Login() {
  const { login, notice, config, clearNotice } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [form, setForm] = useState({ email: "", password: "", remember: false });
  const [showHelp, setShowHelp] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const { submit, pending, errors, formError, formRef } = useSubmit(async () => {
    await login(form);
    clearNotice();
    navigate(safeNext(params.get("next")), { replace: true });
  });

  return (
    <AuthLayout title="Sign in" subtitle="Welcome back. Sign in to continue to WorkforceOS."
      footer={config?.registration_enabled ? <>New to WorkforceOS? <Link to="/register">Create an account</Link></> : null}>
      {notice && !formError && <div className="auth-notice" role="status"><Info size={16} aria-hidden="true" />{notice}</div>}
      <form ref={formRef} onSubmit={submit} noValidate className="auth-form">
        <FormAlert>{formError && !Object.keys(errors).length ? formError : ""}</FormAlert>
        <FormField label="Email" required error={errors.email}>
          <input className="input" type="email" autoComplete="username" value={form.email} onChange={set("email")} autoFocus />
        </FormField>
        <FormField label="Password" required error={errors.password}>
          <PasswordInput value={form.password} onChange={set("password")} />
        </FormField>
        <div className="auth-row">
          <label className="checkbox">
            <input type="checkbox" checked={form.remember} onChange={(e) => setForm({ ...form, remember: e.target.checked })} />
            Keep me signed in for 30 days
          </label>
          <button type="button" className="link-btn subtle" aria-expanded={showHelp} onClick={() => setShowHelp(!showHelp)}>
            Forgot password?
          </button>
        </div>
        {showHelp && (
          <p className="auth-help">
            WorkforceOS doesn't send e-mails yet. Ask an administrator to create a <strong>password-reset link</strong> for you
            (Administration → Users). The link works once and expires after an hour.
          </p>
        )}
        <Button variant="primary" type="submit" loading={pending} className="auth-submit">Sign in</Button>
      </form>
    </AuthLayout>
  );
}
