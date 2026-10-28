import type { AppStatus, RecommendedAction } from "@/api/types";

export const STATUS_LABEL: Record<AppStatus, string> = {
  saved: "Saved",
  tailoring: "Tailoring",
  ready_for_review: "Ready for review",
  awaiting_approval: "Awaiting your approval",
  approved: "Approved",
  handoff_opened: "Employer form opened",
  awaiting_user_confirmation: "Awaiting your confirmation",
  submitted_confirmed: "Submitted (confirmed)",
  interviewing: "Interviewing",
  offer: "Offer",
  accepted: "Accepted",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
  declined: "Declined",
  ghosted: "No response",
};

export const ACTION_LABEL: Record<RecommendedAction, string> = {
  apply: "Apply",
  apply_after_tailoring: "Apply after tailoring",
  research_first: "Research first",
  skip: "Skip",
};

export function statusLabel(s: string): string {
  return STATUS_LABEL[s as AppStatus] ?? humanize(s);
}

export function humanize(s: string): string {
  const t = s.replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export function formatDate(iso: string | null | undefined, withTime = false): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

export function formatPercent(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function formatSalary(min: number | null, max: number | null, currency: string | null): string | null {
  if (min === null && max === null) return null;
  const fmt = (n: number) => n.toLocaleString();
  const cur = currency ? `${currency} ` : "";
  if (min !== null && max !== null) return `${cur}${fmt(min)}–${fmt(max)}`;
  return `${cur}${fmt((min ?? max) as number)}`;
}

export function scoreTone(score: number | undefined | null): "success" | "warning" | "danger" | "neutral" {
  if (score === null || score === undefined) return "neutral";
  if (score >= 70) return "success";
  if (score >= 50) return "warning";
  return "danger";
}

export function splitList(s: string): string[] {
  return s
    .split(/[,\n]/)
    .map((x) => x.trim())
    .filter(Boolean);
}
