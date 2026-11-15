export const STATUS_LABELS = {
  // job
  draft: "Draft", open: "Open", closed: "Closed", archived: "Archived",
  // application
  applied: "Applied", screening: "Screening", interview: "Interview", offer: "Offer", hired: "Hired", rejected: "Rejected",
  // employee
  active: "Active", on_leave: "On leave", terminated: "Terminated",
};
export const TYPE_LABELS = { full_time: "Full-time", part_time: "Part-time", contract: "Contract", internship: "Internship" };
export const SOURCE_LABELS = { careers_page: "Careers page", referral: "Referral", linkedin: "LinkedIn", agency: "Agency", other: "Other" };

export const BADGE_TONE = {
  open: "success", draft: "neutral", closed: "warning", archived: "neutral",
  applied: "neutral", screening: "info", interview: "accent", offer: "warning", hired: "success", rejected: "danger",
  active: "success", on_leave: "warning", terminated: "danger",
};

/** "2026-03-01" (a plain date from the API) -> "Mar 1, 2026" without time-zone shifting. */
export const formatDay = (yyyyMmDd) => {
  const [y, m, d] = yyyyMmDd.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
};

/** Today's date as "YYYY-MM-DD" in the viewer's time zone (for date inputs). */
export const todayIso = () => {
  const t = new Date();
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`;
};

export const label = (map, key) => map[key] ?? key;

export const formatDate = (iso) =>
  new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });

export function timeAgo(iso) {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} hr ago`;
  const days = Math.round(hrs / 24);
  return days < 30 ? `${days} day${days === 1 ? "" : "s"} ago` : formatDate(iso);
}

export const initials = (name) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("");
