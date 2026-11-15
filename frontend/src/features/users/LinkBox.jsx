import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button } from "../../components/ui";
import { formatDate } from "../../lib/format";

/** Shows a one-time link (invitation or password reset) with a copy button. */
export default function LinkBox({ link, label }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(link.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard blocked: the field is selectable */
    }
  }
  return (
    <div className="stack" style={{ gap: 8 }}>
      <label className="section-title" htmlFor="one-time-link" style={{ margin: 0 }}>{label}</label>
      <div className="copy-box">
        <input id="one-time-link" className="input" readOnly value={link.url} onFocus={(e) => e.target.select()} />
        <Button icon={copied ? Check : Copy} onClick={copy}>{copied ? "Copied" : "Copy"}</Button>
      </div>
      <div className="warning-box">Works once, until {formatDate(link.expires_at)} {new Date(link.expires_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}.
        Give it to the person privately (not in a public channel). WorkforceOS doesn't e-mail it.</div>
    </div>
  );
}
