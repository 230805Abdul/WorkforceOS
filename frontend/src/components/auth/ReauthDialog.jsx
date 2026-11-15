import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import Modal from "../ui/Modal";
import { Button, FormAlert, FormField } from "../ui";
import PasswordInput from "./PasswordInput";
import { useSubmit } from "../../hooks/useSubmit";
import { api } from "../../services/api";

/** "Confirm your password" before a high-impact action (changing roles, disabling accounts, reset links...).
 *  Shown automatically when the API answers reauth_required; the original action is retried afterwards. */
export default function ReauthDialog({ minutes, onDone }) {
  const [password, setPassword] = useState("");
  const { submit, pending, errors, formError, formRef } = useSubmit(async () => {
    await api.auth.reauthenticate({ password });
    onDone(true);
  });
  return (
    <Modal size="narrow" title="Confirm your password" busy={pending} onClose={() => onDone(false)}
      description={`This is a sensitive action. Confirm it's really you; you won't be asked again for ${minutes ?? 10} minutes.`}
      footer={<>
        <Button onClick={() => onDone(false)} disabled={pending}>Cancel</Button>
        <Button variant="primary" icon={ShieldCheck} type="submit" form="reauth-form" loading={pending}>Confirm</Button>
      </>}>
      <form id="reauth-form" ref={formRef} onSubmit={submit} noValidate>
        <FormAlert>{formError && !Object.keys(errors).length ? formError : ""}</FormAlert>
        <FormField label="Your password" required error={errors.password}>
          <PasswordInput value={password} onChange={(e) => setPassword(e.target.value)} />
        </FormField>
      </form>
    </Modal>
  );
}
