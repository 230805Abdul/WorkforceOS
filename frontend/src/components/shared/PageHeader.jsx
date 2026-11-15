import { useEffect } from "react";

export default function PageHeader({ title, description, actions }) {
  useEffect(() => {
    document.title = `${title} · WorkforceOS`;
  }, [title]);
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}
