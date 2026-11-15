import { useEffect, useRef, useState } from "react";

/**
 * Form submission helper: blocks double submits, captures API validation errors
 * per field, and moves focus to the first invalid field.
 */
export function useSubmit(action) {
  const [pending, setPending] = useState(false);
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState("");
  const formRef = useRef(null);
  const busy = useRef(false);

  useEffect(() => {
    if (Object.keys(errors).length) formRef.current?.querySelector('[aria-invalid="true"]')?.focus();
  }, [errors]);

  async function submit(e) {
    e?.preventDefault();
    if (busy.current) return;
    busy.current = true;
    setPending(true);
    setErrors({});
    setFormError("");
    try {
      await action();
    } catch (err) {
      setErrors(err.errors ?? {});
      setFormError(err.message);
    } finally {
      busy.current = false;
      setPending(false);
    }
  }
  return { submit, pending, errors, formError, formRef };
}
