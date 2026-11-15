import { Badge } from "../ui";
import { BADGE_TONE, STATUS_LABELS } from "../../lib/format";

export default function StatusBadge({ status }) {
  return <Badge tone={BADGE_TONE[status] ?? "neutral"}>{STATUS_LABELS[status] ?? status}</Badge>;
}
