import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2 } from "lucide-react";
import AuthLayout from "../../components/auth/AuthLayout";
import PasswordInput from "../../components/auth/PasswordInput";
import { Button, FormAlert, FormField } from "../../components/ui";
import { EmptyState } from "../../components/shared/State";
import { useAuth } from "../../auth/AuthContext";
import { useSubmit } from "../../hooks/useSubmit";
import { api } from "../../services/api";

/** Opened from a reset/invitation link an administrator handed out: /reset-password?token=... */
export default function ResetPassword() {
  const { config, status } = useAuth();
  // Read the secret token once, then remove it from the address bar (history, screenshots, shoulder-surfing).
  const [token] = useState(() => new URLSearchParams(window.location.search).get("token") || "");
  useEffect(() => {
    if (token) window.history.replaceState(null, "", window.location.pathname);
  }, [token]);
  const [form, setForm] = useState({ new_password: "", new_password_confirm: "" });
  const [done, setDone] = useState(false);

  const { submit, pending, errors, formError, formRef } = useSubmit(async () => {
    await api.auth.resetPassword({ token, ...form });
    setDone(true);
  });

  if (!token) {
    return (
      <AuthLayout title="Reset link missing" footer={<Link to="/login">Back to sign in</Link>}>
        <p>Open the full link you received from your administrator. It contains a one-time code.</p>
      </AuthLayout>
    );
  }
  if (done) {
    return (
      <AuthLayout title="Password set" footer={null}>
        <EmptyState icon={CheckCircle2} title="Your new password is ready"
          message={status === "authenticated" ? "Other browsers were signed out." : "Sign in with your e-mail and new password."}
          action={<Link className="btn btn-primary" to="/login">Go to sign in</Link>} />
      </AuthLayout>
    );
  }
  return (
    <AuthLayout title="Choose a new password" subtitle="This link works once. Afterwards, every browser signed in to your account is signed out."
      footer={<Link to="/login">Back to sign in</Link>}>
      <form ref={formRef} onSubmit={submit} noValidate className="auth-form">
        <FormAlert>{formError && !Object.keys(errors).length ? formError : ""}</FormAlert>
        <FormField label="New password" required error={errors.new_password} hint={config?.password_policy?.text}>
          <PasswordInput autoComplete="new-password" value={form.new_password} onChange={(e) => setForm({ ...form, new_password: e.target.value })} autoFocus />
        </FormField>
        <FormField label="Confirm new password" required error={errors.new_password_confirm}>
          <PasswordInput autoComplete="new-password" value={form.new_password_confirm} onChange={(e) => setForm({ ...form, new_password_confirm: e.target.value })} />
        </FormField>
        <Button variant="primary" type="submit" loading={pending} className="auth-submit">Set password</Button>
      </form>
    </AuthLayout>
  );
}
