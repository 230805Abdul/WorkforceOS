import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

/** Password field with a show/hide toggle. Extra props (id, aria-*, value, onChange...) go to the <input>. */
export default function PasswordInput({ autoComplete = "current-password", ...rest }) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="password-input">
      <input className="input" type={visible ? "text" : "password"} autoComplete={autoComplete} spellCheck={false} {...rest} />
      <button type="button" className="password-toggle" onClick={() => setVisible(!visible)}
        aria-label={visible ? "Hide password" : "Show password"} aria-pressed={visible}>
        {visible ? <EyeOff size={17} aria-hidden="true" /> : <Eye size={17} aria-hidden="true" />}
      </button>
    </div>
  );
}
