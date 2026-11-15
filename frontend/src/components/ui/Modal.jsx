import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { IconButton } from "./index";

// Open dialogs, innermost last: only the TOP one reacts to Escape/Tab (e.g. the password prompt over "Manage user").
const openDialogs = [];

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Accessible dialog: focus moves in, Tab is trapped, Escape closes, focus returns to the opener. */
export default function Modal({ title, description, onClose, footer, size, children, busy = false }) {
  const titleId = useId();
  const descId = useId();
  const ref = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = busy ? () => {} : onClose;

  useEffect(() => {
    const opener = document.activeElement;
    const node = ref.current;
    const first = node.querySelector(".dialog-body input, .dialog-body select, .dialog-body textarea") || node.querySelector(FOCUSABLE);
    first?.focus();
    document.body.style.overflow = "hidden";

    const me = Symbol("dialog");
    openDialogs.push(me);
    const onKey = (e) => {
      if (openDialogs[openDialogs.length - 1] !== me) return;
      if (e.key === "Escape") {
        e.stopPropagation();
        closeRef.current();
      } else if (e.key === "Tab") {
        const items = [...node.querySelectorAll(FOCUSABLE)];
        if (!items.length) return;
        const [head, tail] = [items[0], items[items.length - 1]];
        if (e.shiftKey && document.activeElement === head) { e.preventDefault(); tail.focus(); }
        else if (!e.shiftKey && document.activeElement === tail) { e.preventDefault(); head.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      openDialogs.splice(openDialogs.indexOf(me), 1);
      document.removeEventListener("keydown", onKey);
      if (!openDialogs.length) document.body.style.overflow = "";
      opener?.focus?.();
    };
  }, []);

  return createPortal(
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && closeRef.current()}>
      <div ref={ref} className={`dialog ${size ?? ""}`} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={description ? descId : undefined}>
        <div className="dialog-head">
          <div>
            <h2 id={titleId}>{title}</h2>
            {description && <p id={descId}>{description}</p>}
          </div>
          <IconButton icon={X} label="Close dialog" onClick={() => closeRef.current()} />
        </div>
        <div className="dialog-body">{children}</div>
        {footer && <div className="dialog-foot">{footer}</div>}
      </div>
    </div>,
    document.body
  );
}
