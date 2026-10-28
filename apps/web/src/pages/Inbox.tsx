import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router";
import { api, errorMessage } from "@/api/client";
import type { ImportResult, TriageItem } from "@/api/types";
import { ScamPanel } from "@/components/domain";
import { useToast } from "@/components/Toast";
import { Badge, Button, Card, EmptyState, PageHeader, QueryView, Select } from "@/components/ui";
import { formatDate, formatPercent, humanize, statusLabel } from "@/lib/format";

const CLASS_TONE: Record<string, "success" | "info" | "warning" | "danger" | "neutral" | "primary"> = {
  interview_invite: "success",
  assessment: "primary",
  rejection: "danger",
  recruiter_reply: "info",
  job_alert: "warning",
  other: "neutral",
};

export default function Inbox() {
  const qc = useQueryClient();
  const toast = useToast();
  const [status, setStatus] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const q = useQuery({ queryKey: ["triage", status], queryFn: () => api.get<TriageItem[]>("/api/triage", { status }) });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["triage"] });
    void qc.invalidateQueries({ queryKey: ["dashboard"] });
    void qc.invalidateQueries({ queryKey: ["applications"] });
  };
  const upload = useMutation({
    mutationFn: (f: File) => api.upload<TriageItem[]>("/api/triage/upload", f),
    onSuccess: (r) => {
      toast.success(`Classified ${r.length} email(s)`);
      refresh();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <>
      <PageHeader
        title="Inbox"
        description="Upload emails (.eml or .mbox) and JobPilot suggests tracker updates with evidence. Nothing changes until you accept a suggestion, and nothing is ever sent."
        actions={
          <>
            <input
              ref={fileRef}
              type="file"
              className="sr-only"
              aria-label="Email file"
              accept=".eml,.mbox,message/rfc822"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) upload.mutate(f);
                e.target.value = "";
              }}
            />
            <Button icon={<Upload className="h-4 w-4" aria-hidden />} loading={upload.isPending} onClick={() => fileRef.current?.click()}>
              Upload emails
            </Button>
          </>
        }
      />
      <div className="mb-4 flex items-center gap-2">
        <Select aria-label="Filter by review status" value={status} onChange={(e) => setStatus(e.target.value)} className="w-56">
          <option value="">All emails</option>
          <option value="pending">Needs review</option>
          <option value="accepted">Accepted</option>
          <option value="dismissed">Dismissed</option>
          <option value="info">Informational</option>
        </Select>
      </div>
      <QueryView
        query={q}
        isEmpty={(d) => d.length === 0}
        empty={
          <EmptyState title="No emails yet">
            Save an email from your mail client as .eml (or export a folder as .mbox) and upload it. Gmail/Outlook connection isn't available in this build.
          </EmptyState>
        }
      >
        {(list) => (
          <ul className="space-y-4">
            {list.map((m) => (
              <TriageCard key={m.id} m={m} onChange={refresh} />
            ))}
          </ul>
        )}
      </QueryView>
    </>
  );
}

function TriageCard({ m, onChange }: { m: TriageItem; onChange: () => void }) {
  const toast = useToast();
  const accept = useMutation({
    mutationFn: () => api.post<{ application_status: string }>(`/api/triage/${m.id}/accept`),
    onSuccess: (r) => {
      toast.success(`Application moved to ${statusLabel(r.application_status)}`);
      onChange();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const dismiss = useMutation({ mutationFn: () => api.post(`/api/triage/${m.id}/dismiss`), onSuccess: onChange, onError: (e) => toast.error(errorMessage(e)) });
  const importJobs = useMutation({
    mutationFn: () => api.post<ImportResult>(`/api/triage/${m.id}/import-jobs`),
    onSuccess: (r) => {
      toast.success(`Imported ${r.counts.created} job(s) from this alert`);
      onChange();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <li>
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="font-medium">{m.subject || "(no subject)"}</p>
            <p className="text-xs text-subtle">
              {m.sender} · {formatDate(m.received_at, true)}
            </p>
          </div>
          <div className="flex flex-wrap gap-1">
            <Badge tone={CLASS_TONE[m.classification] ?? "neutral"}>{humanize(m.classification)}</Badge>
            <Badge>{formatPercent(m.confidence)} confidence</Badge>
            <Badge tone={m.review_status === "pending" ? "warning" : "neutral"}>{humanize(m.review_status)}</Badge>
          </div>
        </div>
        <blockquote className="mt-3 border-l-2 border-border pl-3 text-sm text-subtle">
          <span className="text-xs font-medium uppercase">Evidence</span>
          <br />“{m.evidence}”
        </blockquote>
        {m.suggested_status && m.application_id && (
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded border border-primary/40 bg-primary/5 p-3 text-sm">
            <span className="flex-1">
              Suggested: move{" "}
              <Link className="font-medium text-primary hover:underline" to={`/applications/${m.application_id}`}>
                the matching application
              </Link>{" "}
              to <strong>{statusLabel(m.suggested_status)}</strong>.
            </span>
            {m.review_status === "pending" && (
              <>
                <Button size="sm" icon={<Check className="h-4 w-4" aria-hidden />} loading={accept.isPending} onClick={() => accept.mutate()}>
                  Accept
                </Button>
                <Button size="sm" variant="ghost" icon={<X className="h-4 w-4" aria-hidden />} loading={dismiss.isPending} onClick={() => dismiss.mutate()}>
                  Dismiss
                </Button>
              </>
            )}
          </div>
        )}
        {!m.suggested_status && m.application_id && (
          <p className="mt-3 text-sm">
            Related to{" "}
            <Link className="text-primary hover:underline" to={`/applications/${m.application_id}`}>
              an application
            </Link>
            .
          </p>
        )}
        {m.classification === "job_alert" && (
          <Button size="sm" variant="secondary" className="mt-3" loading={importJobs.isPending} onClick={() => importJobs.mutate()}>
            Import jobs from this alert
          </Button>
        )}
        {m.draft_reply && <DraftReply text={m.draft_reply} />}
        {m.scam_report.level !== "none" && (
          <div className="mt-3">
            <ScamPanel report={m.scam_report} />
          </div>
        )}
      </Card>
    </li>
  );
}

function DraftReply({ text }: { text: string }) {
  const toast = useToast();
  return (
    <details className="mt-3 text-sm">
      <summary className="cursor-pointer font-medium">Draft reply (copy and send yourself)</summary>
      <pre className="mt-2 whitespace-pre-wrap rounded bg-muted p-3 font-sans">{text}</pre>
      <Button
        size="sm"
        variant="secondary"
        className="mt-2"
        icon={<Copy className="h-4 w-4" aria-hidden />}
        onClick={() =>
          void navigator.clipboard.writeText(text).then(
            () => toast.success("Copied to clipboard"),
            () => toast.error("Couldn't access the clipboard"),
          )
        }
      >
        Copy
      </Button>
    </details>
  );
}
