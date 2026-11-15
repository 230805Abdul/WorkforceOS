import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { CheckCircle2, XCircle, X } from "lucide-react";
import { IconButton } from "./index";

const ToastContext = createContext(null);
export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const dismiss = useCallback((id) => setItems((xs) => xs.filter((x) => x.id !== id)), []);
  const push = useCallback((type, message) => {
    const id = crypto.randomUUID();
    setItems((xs) => [...xs, { id, type, message }]);
    setTimeout(() => dismiss(id), type === "error" ? 7000 : 4000);
  }, [dismiss]);
  const api = useMemo(() => ({ success: (m) => push("success", m), error: (m) => push("error", m) }), [push]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.type}`}>
            {t.type === "success" ? <CheckCircle2 className="toast-icon" size={18} aria-hidden="true" /> : <XCircle className="toast-icon" size={18} aria-hidden="true" />}
            <p>{t.message}</p>
            <IconButton icon={X} label="Dismiss notification" onClick={() => dismiss(t.id)} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
