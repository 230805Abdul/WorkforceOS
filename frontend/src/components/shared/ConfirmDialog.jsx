import { useState } from "react";
import Modal from "../ui/Modal";
import { Button } from "../ui";

/** Confirmation before destructive actions. `onConfirm` may be async; errors are handled by the caller. */
export default function ConfirmDialog({ title, children, confirmLabel = "Delete", onConfirm, onClose }) {
  const [pending, setPending] = useState(false);
  async function confirm() {
    setPending(true);
    try {
      await onConfirm();
    } finally {
      setPending(false);
    }
  }
  return (
    <Modal
      size="narrow"
      title={title}
      onClose={onClose}
      busy={pending}
      footer={
        <>
          <Button onClick={onClose} disabled={pending}>Cancel</Button>
          <Button variant="danger" onClick={confirm} loading={pending}>{confirmLabel}</Button>
        </>
      }
    >
      {children}
    </Modal>
  );
}
