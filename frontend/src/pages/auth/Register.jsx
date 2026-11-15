import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import AuthLayout from "../../components/auth/AuthLayout";
import PasswordInput from "../../components/auth/PasswordInput";
import { Button, FormAlert, FormField } from "../../components/ui";
import { useToast } from "../../components/ui/Toast";
import { useAuth } from "../../auth/AuthContext";
import { useSubmit } from "../../hooks/useSubmit";

export default function Register() {
  const { register, config } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: "", email: "", password: "", password_confirm: "" });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const { submit, pending, errors, formError, formRef } = useSubmit(async () => {
    await register(form);
    toast.success("Your account is ready. An administrator can give you more access.");
    navigate("/", { replace: true });
  });

  if (config && !config.registration_enabled) return <Navigate to="/login" replace />;

  return (
    <AuthLayout title="Create your account" subtitle="New accounts start with Employee access. An administrator can grant more."
      footer={<>Already have an account? <Link to="/login">Sign in</Link></>}>
      <form ref={formRef} onSubmit={submit} noValidate className="auth-form">
        <FormAlert>{formError && !Object.keys(errors).length ? formError : ""}</FormAlert>
        <FormField label="Full name" required error={errors.full_name}>
          <input className="input" autoComplete="name" value={form.full_name} onChange={set("full_name")} autoFocus maxLength={120} />
        </FormField>
        <FormField label="Email" required error={errors.email}>
          <input className="input" type="email" autoComplete="email" value={form.email} onChange={set("email")} />
        </FormField>
        <FormField label="Password" required error={errors.password} hint={config?.password_policy?.text}>
          <PasswordInput autoComplete="new-password" value={form.password} onChange={set("password")} />
        </FormField>
        <FormField label="Confirm password" required error={errors.password_confirm}>
          <PasswordInput autoComplete="new-password" value={form.password_confirm} onChange={set("password_confirm")} />
        </FormField>
        <Button variant="primary" type="submit" loading={pending} className="auth-submit">Create account</Button>
      </form>
    </AuthLayout>
  );
}
