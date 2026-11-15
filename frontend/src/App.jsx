import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { api } from "./services/api";
import { useFetch } from "./hooks/useFetch";
import { MetaProvider } from "./lib/MetaContext";
import { ToastProvider } from "./components/ui/Toast";
import { Spinner } from "./components/ui";
import { ErrorState } from "./components/shared/State";
import AppShell from "./components/layout/AppShell";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { PublicOnly, RequireAuth, RequirePermission } from "./auth/guards";
import Login from "./pages/auth/Login";
import Register from "./pages/auth/Register";
import ResetPassword from "./pages/auth/ResetPassword";
import Dashboard from "./pages/Dashboard";
import Jobs from "./pages/Jobs";
import Candidates from "./pages/Candidates";
import Pipeline from "./pages/Pipeline";
import Employees from "./pages/Employees";
import Departments from "./pages/Departments";
import Profile from "./pages/Profile";
import Users from "./pages/admin/Users";
import Roles from "./pages/admin/Roles";
import AuditLog from "./pages/admin/AuditLog";

function Unreachable({ error, onRetry }) {
  return (
    <div className="content" style={{ maxWidth: 560, paddingTop: 80 }}>
      <div className="card">
        <ErrorState error={error} onRetry={onRetry} />
        <p className="muted" style={{ textAlign: "center", padding: "0 24px 28px" }}>
          Start it with <code>uvicorn app.main:app --reload</code> inside <code>backend/</code>, then retry.
        </p>
      </div>
    </div>
  );
}

/** Signed-in area: load the dropdown option lists once, then show the app shell. */
function SignedInApp() {
  const { data: meta, error, refetch } = useFetch((signal) => api.meta(signal), []);
  if (error) return <Unreachable error={error} onRetry={refetch} />;
  if (!meta) return <div className="state" role="status"><Spinner /><p>Loading WorkforceOS…</p></div>;
  return (
    <MetaProvider value={meta}>
      <AppShell />
    </MetaProvider>
  );
}

/** "/" -> the dashboard if you may see it, otherwise your profile (e.g. the Employee role). */
function Home() {
  const { can } = useAuth();
  return can("dashboard:view") ? <Dashboard /> : <Navigate to="/profile" replace />;
}

function AppRoutes() {
  const { status, error, retry } = useAuth();
  if (status === "error") return <Unreachable error={error} onRetry={retry} />;
  const guard = (perm, element) => <RequirePermission perm={perm}>{element}</RequirePermission>;
  return (
    <Routes>
      <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
      <Route path="/register" element={<PublicOnly><Register /></PublicOnly>} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route element={<RequireAuth><SignedInApp /></RequireAuth>}>
        <Route index element={<Home />} />
        <Route path="profile" element={guard("profile:own", <Profile />)} />
        <Route path="employees" element={guard("employees:read", <Employees />)} />
        <Route path="departments" element={guard("departments:read", <Departments />)} />
        <Route path="jobs" element={guard("jobs:read", <Jobs />)} />
        <Route path="candidates" element={guard("candidates:read", <Candidates />)} />
        <Route path="pipeline" element={guard("applications:read", <Pipeline />)} />
        <Route path="admin/users" element={guard("users:read", <Users />)} />
        <Route path="admin/roles" element={<RequirePermission any={["users:read", "roles:assign", "roles:manage"]}><Roles /></RequirePermission>} />
        <Route path="admin/audit" element={guard("audit:read", <AuditLog />)} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
