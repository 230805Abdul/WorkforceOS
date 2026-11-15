import { AlertTriangle, Inbox } from "lucide-react";
import { Button } from "../ui";

/** Empty and error states used inside cards and tables. */
export function EmptyState({ title, message, action, icon: Icon = Inbox }) {
  return (
    <div className="state">
      <span className="state-icon"><Icon size={22} aria-hidden="true" /></span>
      <h3>{title}</h3>
      {message && <p>{message}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="state error" role="alert">
      <span className="state-icon"><AlertTriangle size={22} aria-hidden="true" /></span>
      <h3>Something went wrong</h3>
      <p>{error?.message ?? "Unexpected error."}</p>
      {onRetry && <Button onClick={onRetry}>Try again</Button>}
    </div>
  );
}
