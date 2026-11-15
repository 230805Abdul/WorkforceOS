import { Navigate, useLocation } from "react-router-dom";
import { ShieldAlert } from "lucide-react";
import { useAuth } from "./AuthContext";
import { Spinner } from "../components/ui";
import { EmptyState } from "../components/shared/State";

export function FullPageSpinner({ label = "Checking your session…" }) {
  return <div className="state" role="status" style={{ minHeight: "60vh", justifyContent: "center" }}><Spinner /><p>{label}</p></div>;
}

/** Pages behind sign-in. Not signed in -> /login?next=<where you wanted to go>. */
export function RequireAuth({ children }) {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "loading") return <FullPageSpinner />;
  if (status !== "authenticated") {
    const next = location.pathname + location.search;
    return <Navigate to={next === "/" ? "/login" : `/login?next=${encodeURIComponent(next)}`} replace />;
  }
  return children;
}

/** Pages for signed-OUT visitors only (login, register). Already signed in -> into the app. */
export function PublicOnly({ children }) {
  const { status } = useAuth();
  if (status === "loading") return <FullPageSpinner />;
  if (status === "authenticated") return <Navigate to="/" replace />;
  return children;
}

/** Shown when someone opens a page they may not use (e.g. typed the URL). The API would refuse anyway. */
export function Forbidden() {
  return (
    <div className="card" style={{ maxWidth: 560, margin: "40px auto" }}>
      <EmptyState icon={ShieldAlert} title="You don't have access to this page"
        message="Your role doesn't include this part of WorkforceOS. If you need it, ask an administrator." />
    </div>
  );
}

/** Route-level permission check: <RequirePermission perm="employees:read"><Employees /></RequirePermission> */
export function RequirePermission({ perm, any, children }) {
  const { can, canAny } = useAuth();
  const allowed = perm ? can(perm) : canAny(...any);
  return allowed ? children : <Forbidden />;
}

/** Inline helper: renders children only with the permission. */
export function Can({ perm, children, fallback = null }) {
  const { can } = useAuth();
  return can(perm) ? children : fallback;
}
