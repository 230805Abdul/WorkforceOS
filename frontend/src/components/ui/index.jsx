import { cloneElement, useId } from "react";
import { AlertCircle } from "lucide-react";

export const Spinner = () => <span className="spinner" aria-hidden="true" />;

/** variant: primary | secondary (default) | danger | ghost */
export function Button({ variant = "secondary", size, loading, icon: Icon, children, className = "", ...rest }) {
  const cls = ["btn", variant !== "secondary" && `btn-${variant}`, size === "sm" && "btn-sm", className].filter(Boolean).join(" ");
  return (
    <button type="button" className={cls} disabled={loading || rest.disabled} {...rest}>
      {loading ? <Spinner /> : Icon ? <Icon size={16} aria-hidden="true" /> : null}
      {children}
    </button>
  );
}

export function IconButton({ icon: Icon, label, danger, ...rest }) {
  return (
    <button type="button" className={`icon-btn ${danger ? "danger" : ""}`} aria-label={label} title={label} {...rest}>
      <Icon size={17} aria-hidden="true" />
    </button>
  );
}

export function Badge({ tone = "neutral", children }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

/** Wraps one input/select/textarea with a label, hint and an associated error message. */
export function FormField({ label, error, hint, required, className = "", children }) {
  const id = useId();
  const describedBy = [error && `${id}-err`, hint && `${id}-hint`].filter(Boolean).join(" ") || undefined;
  return (
    <div className={`field ${className}`}>
      <label htmlFor={id}>
        {label}
        {required && <span className="req" aria-hidden="true"> *</span>}
      </label>
      {cloneElement(children, { id, "aria-invalid": error ? true : undefined, "aria-describedby": describedBy, "aria-required": required || undefined })}
      {hint && !error && <span className="field-hint" id={`${id}-hint`}>{hint}</span>}
      {error && (
        <span className="field-error" id={`${id}-err`}>
          <AlertCircle size={15} aria-hidden="true" style={{ marginTop: 2, flex: "none" }} />
          {error}
        </span>
      )}
    </div>
  );
}

export function FormAlert({ children }) {
  if (!children) return null;
  return (
    <div className="form-alert" role="alert">
      <AlertCircle size={16} aria-hidden="true" style={{ marginTop: 3, flex: "none" }} />
      <span>{children}</span>
    </div>
  );
}
