import { useEffect } from "react";
import { Building2, GitPullRequestArrow, ShieldCheck, Waypoints } from "lucide-react";

/** Two-column frame for the signed-out pages: brand panel (same navy as the sidebar) + form card. */
export default function AuthLayout({ title, subtitle, children, footer }) {
  useEffect(() => {
    document.title = `${title} · WorkforceOS`;
  }, [title]);
  return (
    <div className="auth-page">
      <aside className="auth-brand" aria-hidden="true">
        <div className="brand"><span className="brand-mark"><Waypoints size={18} /></span><span>WorkforceOS</span></div>
        <div className="auth-brand-copy">
          <h2>Your people and your hiring, in one place.</h2>
          <ul>
            <li><Building2 size={18} /> Departments and employee records</li>
            <li><GitPullRequestArrow size={18} /> Jobs, candidates and the hiring pipeline</li>
            <li><ShieldCheck size={18} /> Role-based access for every team</li>
          </ul>
        </div>
        <p className="auth-brand-foot">Local development build</p>
      </aside>
      <main className="auth-main" id="main">
        <div className="auth-card">
          <div className="auth-mobile-brand"><span className="brand-mark"><Waypoints size={18} aria-hidden="true" /></span>WorkforceOS</div>
          <h1>{title}</h1>
          {subtitle && <p className="auth-subtitle">{subtitle}</p>}
          {children}
        </div>
        {footer && <p className="auth-footer">{footer}</p>}
      </main>
    </div>
  );
}
