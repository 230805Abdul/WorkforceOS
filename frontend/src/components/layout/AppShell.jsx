import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Briefcase, Building2, ChevronsLeft, ChevronsRight, CircleUser, GitPullRequestArrow, KeyRound, LayoutDashboard, LogOut, Menu, Moon, RotateCcw, ScrollText, ShieldCheck, Sun, UserCog, UserRound, Users, Waypoints } from "lucide-react";
import { api } from "../../services/api";
import { useTheme } from "../../hooks/useTheme";
import { useIsMobile } from "../../hooks/useIsMobile";
import { useToast } from "../ui/Toast";
import { IconButton } from "../ui";
import ConfirmDialog from "../shared/ConfirmDialog";
import { useMeta } from "../../lib/MetaContext";
import { useAuth } from "../../auth/AuthContext";
import { initials } from "../../lib/format";

// Each item names the permission needed to see it. Hiding is only for clarity: the API checks every request anyway.
const NAV = [
  { heading: "Overview", items: [{ to: "/", label: "Dashboard", icon: LayoutDashboard, end: true, perm: "dashboard:view" }] },
  {
    heading: "Workforce",
    items: [
      { to: "/employees", label: "Employees", icon: UserRound, perm: "employees:read" },
      { to: "/departments", label: "Departments", icon: Building2, perm: "departments:read" },
    ],
  },
  {
    heading: "Recruiting",
    items: [
      { to: "/jobs", label: "Jobs", icon: Briefcase, perm: "jobs:read" },
      { to: "/candidates", label: "Candidates", icon: Users, perm: "candidates:read" },
      { to: "/pipeline", label: "Pipeline", icon: GitPullRequestArrow, perm: "applications:read" },
    ],
  },
  {
    heading: "Administration",
    items: [
      { to: "/admin/users", label: "Users", icon: UserCog, perm: "users:read" },
      { to: "/admin/roles", label: "Roles", icon: KeyRound, any: ["users:read", "roles:assign", "roles:manage"] },
      { to: "/admin/audit", label: "Audit log", icon: ScrollText, perm: "audit:read" },
    ],
  },
  { heading: "You", items: [{ to: "/profile", label: "My profile", icon: CircleUser, perm: "profile:own" }] },
];

function ApiStatus() {
  const [state, setState] = useState("checking");
  useEffect(() => {
    let alive = true;
    const check = () =>
      api.health().then(() => alive && setState("ok")).catch((e) => alive && setState(e.status === 503 ? "db-down" : "down"));
    check();
    const t = setInterval(check, 15000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  const text = { ok: "API connected", down: "API offline", "db-down": "Database offline", checking: "Checking API" }[state];
  return <span className={`api-pill ${state === "db-down" ? "down" : state}`} role="status"><i aria-hidden="true" /><span>{text}</span></span>;
}

function ProfileMenu({ onReset, canReset }) {
  const { user, logout, can } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e) => !ref.current?.contains(e.target) && setOpen(false);
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open]);
  const roleNames = user.roles.map((r) => r.label).join(", ") || "No role";
  return (
    <div className="profile" ref={ref}>
      <button type="button" className="profile-btn" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}
        aria-label={`Account menu for ${user.full_name}`}>
        <span className="avatar" aria-hidden="true">{initials(user.full_name)}</span>
        <span className="profile-name">{user.full_name}</span>
      </button>
      {open && (
        <div className="popover" role="menu">
          <div className="popover-head">
            <strong>{user.full_name}</strong>
            <span className="muted" style={{ display: "block", fontSize: 13 }}>{user.email}</span>
            <span className="muted" style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12, marginTop: 4 }}>
              <ShieldCheck size={13} aria-hidden="true" />{roleNames}
            </span>
          </div>
          {can("profile:own") && (
            <Link role="menuitem" className="menu-item" to="/profile" onClick={() => setOpen(false)} style={{ textDecoration: "none", color: "inherit" }}>
              <CircleUser size={16} aria-hidden="true" /> My profile
            </Link>
          )}
          {canReset && (
            <button type="button" role="menuitem" className="menu-item" onClick={() => { setOpen(false); onReset(); }}>
              <RotateCcw size={16} aria-hidden="true" /> Reset demo data
            </button>
          )}
          <button type="button" role="menuitem" className="menu-item"
            onClick={async () => { setOpen(false); await logout(); navigate("/login", { replace: true }); }}>
            <LogOut size={16} aria-hidden="true" /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

export default function AppShell() {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("wos-sidebar") === "collapsed";
    } catch {
      return false; // storage blocked (some privacy modes): just start expanded
    }
  });
  const [mobileOpen, setMobileOpen] = useState(false);
  const [version, setVersion] = useState(0); // bumping this remounts the page so it refetches after a reset
  const [confirmReset, setConfirmReset] = useState(false);
  const [theme, toggleTheme] = useTheme();
  const isMobile = useIsMobile();
  const meta = useMeta();
  const toast = useToast();
  const { can, canAny } = useAuth();
  const nav = NAV.map((g) => ({ ...g, items: g.items.filter((i) => (i.perm ? can(i.perm) : canAny(...i.any))) })).filter((g) => g.items.length);
  const { pathname } = useLocation();

  useEffect(() => setMobileOpen(false), [pathname]);
  useEffect(() => {
    if (!mobileOpen) return;
    const onKey = (e) => e.key === "Escape" && setMobileOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [mobileOpen]);

  const toggleSidebar = () => {
    const next = !collapsed;
    setCollapsed(next);
    try { localStorage.setItem("wos-sidebar", next ? "collapsed" : "expanded"); } catch { /* ignore */ }
  };

  async function resetDemo() {
    try {
      await api.resetDemo();
      setConfirmReset(false);
      setVersion((v) => v + 1);
      toast.success("Demo data has been reset.");
    } catch (e) {
      toast.error(e.message);
    }
  }

  return (
    <div className={`shell ${collapsed ? "is-collapsed" : ""}`}>
      <a className="skip-link" href="#main">Skip to content</a>
      <aside className={`sidebar ${mobileOpen ? "is-open" : ""}`} aria-label="Primary">
        <div className="brand">
          <span className="brand-mark"><Waypoints size={18} aria-hidden="true" /></span>
          <span className="brand-name">WorkforceOS</span>
        </div>
        <nav className="nav" aria-label="Main navigation">
          {nav.map((g) => (
            <div className="nav-group" key={g.heading}>
              <p className="nav-heading">{g.heading}</p>
              {g.items.map(({ to, label, icon: Icon, end }) => (
                <NavLink key={to} to={to} end={end} className="nav-link" title={label}>
                  <Icon size={19} aria-hidden="true" />
                  <span className="nav-label">{label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-foot">
          <p>Local development build.<br />Signed in · data in PostgreSQL.</p>
        </div>
      </aside>
      <div className={`scrim ${mobileOpen ? "is-open" : ""}`} onClick={() => setMobileOpen(false)} aria-hidden="true" />

      <div className="shell-main">
        <header className="topbar">
          <IconButton
            icon={isMobile ? Menu : collapsed ? ChevronsRight : ChevronsLeft}
            label={isMobile ? "Open navigation" : collapsed ? "Expand sidebar" : "Collapse sidebar"}
            onClick={() => (isMobile ? setMobileOpen(true) : toggleSidebar())}
          />
          <div className="topbar-spacer" />
          <ApiStatus />
          <IconButton icon={theme === "dark" ? Sun : Moon} label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"} onClick={toggleTheme} />
          <ProfileMenu canReset={meta.demo_reset_enabled && can("system:demo_reset")} onReset={() => setConfirmReset(true)} />
        </header>
        <main id="main" className="content" tabIndex={-1}>
          <Outlet key={version} />
        </main>
      </div>

      {confirmReset && (
        <ConfirmDialog title="Reset demo data?" confirmLabel="Reset data" onConfirm={resetDemo} onClose={() => setConfirmReset(false)}>
          <p>This permanently deletes <strong>all</strong> departments, employees, jobs, candidates and applications and restores the original sample data. User accounts are kept. This cannot be undone.</p>
        </ConfirmDialog>
      )}
    </div>
  );
}
