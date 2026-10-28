import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, Bell, Check, CheckCircle2, ExternalLink, FileText, Lock, ShieldCheck, Sparkles, XCircle } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError, errorMessage, newIdempotencyKey } from "@/api/client";
import type { ApplicationDetail, DocumentSummary, PreflightCheck, ScreeningAnswer } from "@/api/types";
import { useToast } from "@/components/Toast";
import { Badge, Button, Card, CardTitle, Checkbox, cn, DemoBadge, Field, Input, QueryView, Textarea } from "@/components/ui";
import { formatDate, humanize, statusLabel } from "@/lib/format";

const STEPS = [
  { key: "prepare", label: "Prepare documents", statuses: ["saved", "tailoring"] },
  { key: "review", label: "Review & pre-flight", statuses: ["ready_for_review"] },
  { key: "approve", label: "Approve package", statuses: ["awaiting_approval"] },
  { key: "handoff", label: "Submit on employer site", statuses: ["approved", "handoff_opened", "awaiting_user_confirmation"] },
  { key: "done", label: "Confirmed", statuses: ["submitted_confirmed", "interviewing", "offer", "accepted", "rejected", "declined", "ghosted"] },
];

export default function ApplicationWorkspace() {
  const { appId = "" } = useParams();
  const q = useQuery({ queryKey: ["application", appId], queryFn: () => api.get<ApplicationDetail>(`/api/applications/${appId}`) });
  return (
    <>
      <Link to="/tracker" className="mb-4 inline-flex items-center gap-1 text-sm text-subtle hover:text-fg">
        <ArrowLeft className="h-4 w-4" aria-hidden /> Tracker
      </Link>
      <QueryView query={q} loadingLabel="Loading application">
        {(app) => <Workspace app={app} />}
      </QueryView>
    </>
  );
}

function useAppMutation<TVars = void>(appId: string, fn: (v: TVars) => Promise<unknown>, success?: string) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: fn,
    onSuccess: (data) => {
      if (data && typeof data === "object" && "activity" in data) qc.setQueryData(["application", appId], data);
      else void qc.invalidateQueries({ queryKey: ["application", appId] });
      void qc.invalidateQueries({ queryKey: ["applications"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
      void qc.invalidateQueries({ queryKey: ["documents"] });
      if (success) toast.success(success);
    },
    onError: (e) => {
      void qc.invalidateQueries({ queryKey: ["application", appId] });
      toast.error(errorMessage(e));
    },
  });
}

function Workspace({ app }: { app: ApplicationDetail }) {
  const stepIndex = STEPS.findIndex((s) => s.statuses.includes(app.status));
  const closed = app.status === "withdrawn";
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">
            {app.job.title} {app.is_demo && <DemoBadge />}
          </h1>
          <p className="text-subtle">
            <Link to={`/jobs/${app.job_id}`} className="hover:underline">
              {app.job.company}
            </Link>
            {app.job.location && ` · ${app.job.location}`}
          </p>
        </div>
        <Badge tone={app.status === "submitted_confirmed" ? "success" : "primary"} className="text-sm">
          {statusLabel(app.status)}
        </Badge>
      </div>

      <nav aria-label="Application steps">
        <ol className="grid gap-2 sm:grid-cols-5">
          {STEPS.map((s, i) => {
            const state = closed ? "todo" : i < stepIndex ? "done" : i === stepIndex ? "current" : "todo";
            return (
              <li
                key={s.key}
                aria-current={state === "current" ? "step" : undefined}
                className={cn(
                  "rounded border px-3 py-2 text-sm",
                  state === "done" && "border-success/40 bg-success/5",
                  state === "current" && "border-primary bg-primary/5 font-medium",
                  state === "todo" && "border-border text-subtle",
                )}
              >
                <span className="mr-1 tabular-nums">{i + 1}.</span>
                {s.label}
                {state === "done" && <Check className="ml-1 inline h-4 w-4 text-success" aria-label="done" />}
              </li>
            );
          })}
        </ol>
      </nav>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <StepPanel app={app} />
          <DocumentsCard app={app} />
          <ScreeningCard app={app} />
        </div>
        <div className="space-y-6">
          <NotesCard app={app} />
          <RemindersCard app={app} />
          <ActivityCard app={app} />
        </div>
      </div>
    </div>
  );
}

function StepPanel({ app }: { app: ApplicationDetail }) {
  const [prepKey] = useState(newIdempotencyKey);
  const prepare = useAppMutation(app.id, () => api.post(`/api/applications/${app.id}/prepare`, undefined, { idempotencyKey: `${prepKey}-${app.version}` }), "Tailored resume and cover letter generated");
  const ready = useAppMutation(app.id, () => api.post(`/api/applications/${app.id}/ready`));
  const requestApproval = useAppMutation(app.id, () => api.post(`/api/applications/${app.id}/request-approval`));
  const approve = useAppMutation(app.id, () => api.post(`/api/applications/${app.id}/approve`, { payload_hash: app.approval_payload_hash }), "Approved. Approval is bound to exactly this package.");
  const handoff = useAppMutation(app.id, async () => {
    const r = await api.post<{ url: string | null; instructions: string }>(`/api/applications/${app.id}/handoff`);
    if (r.url) window.open(r.url, "_blank", "noopener,noreferrer");
    return r;
  });
  const [confirmed, setConfirmed] = useState(false);
  const [note, setNote] = useState("");
  const confirm = useAppMutation(app.id, () => api.post(`/api/applications/${app.id}/confirm-submission`, { confirmed: true, note }), "Submission confirmed and recorded");
  const back = useAppMutation(app.id, (status: string) => api.post(`/api/applications/${app.id}/move`, { status }));

  const preflightError = requestApproval.error instanceof ApiError && requestApproval.error.code === "preflight_failed";

  switch (app.status) {
    case "saved":
    case "tailoring":
      return (
        <Card>
          <CardTitle>Step 1 · Prepare documents</CardTitle>
          <p className="mb-3 text-sm text-subtle">
            JobPilot drafts a tailored resume and cover letter using only your confirmed facts. Every claim cites the facts it comes from and is checked by
            the grounding validator. Items that fail are blocked from export.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button icon={<Sparkles className="h-4 w-4" aria-hidden />} loading={prepare.isPending} onClick={() => prepare.mutate()}>
              {app.resume_doc_id ? "Regenerate documents" : "Generate tailored documents"}
            </Button>
            <Button variant="secondary" disabled={!app.resume_doc_id} loading={ready.isPending} onClick={() => ready.mutate()}>
              Mark ready for review
            </Button>
          </div>
        </Card>
      );
    case "ready_for_review":
      return (
        <Card>
          <CardTitle>Step 2 · Review & pre-flight</CardTitle>
          <Preflight checks={app.preflight.checks} />
          {preflightError && (
            <p role="alert" className="mt-3 text-sm text-danger">
              Fix the blocking checks above before requesting approval.
            </p>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            <Button icon={<ShieldCheck className="h-4 w-4" aria-hidden />} disabled={!app.preflight.ok} loading={requestApproval.isPending} onClick={() => requestApproval.mutate()}>
              Request approval
            </Button>
            <Button variant="ghost" onClick={() => back.mutate("tailoring")}>
              Back to editing
            </Button>
          </div>
        </Card>
      );
    case "awaiting_approval":
      return (
        <Card className="border-primary/50">
          <CardTitle>Step 3 · Approve this exact package</CardTitle>
          <p className="mb-3 text-sm">
            Your approval is recorded with a hash of what is shown below. If the resume, cover letter or answers change afterwards, the approval is
            invalidated and you will be asked again.
          </p>
          <ApprovalPayload app={app} />
          <p className="mt-2 break-all font-mono text-xs text-subtle">Package hash: {app.approval_payload_hash}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button icon={<Check className="h-4 w-4" aria-hidden />} loading={approve.isPending} onClick={() => approve.mutate()}>
              I approve this package
            </Button>
            <Button variant="ghost" onClick={() => back.mutate("ready_for_review")}>
              Not yet
            </Button>
          </div>
        </Card>
      );
    case "approved":
    case "handoff_opened":
      return (
        <Card>
          <CardTitle>Step 4 · Submit on the employer's site</CardTitle>
          <p className="mb-3 text-sm">
            JobPilot never submits for you. Open the employer's form, fill it in with your approved documents, and press their submit button yourself.
          </p>
          {app.job.url ? (
            <Button icon={<ExternalLink className="h-4 w-4" aria-hidden />} loading={handoff.isPending} onClick={() => handoff.mutate()}>
              Open employer form
            </Button>
          ) : (
            <>
              <p className="mb-2 text-sm text-warning">This job has no URL. Apply through the channel named in the posting.</p>
              <Button loading={handoff.isPending} onClick={() => handoff.mutate()}>
                I'm applying now
              </Button>
            </>
          )}
        </Card>
      );
    case "awaiting_user_confirmation":
      return (
        <Card className="border-primary/50">
          <CardTitle>Step 4 · Confirm you submitted</CardTitle>
          <p className="mb-3 text-sm">Opening the form doesn't count as applying. Confirm only once you have actually submitted.</p>
          {app.job.url && (
            <a href={app.job.url} target="_blank" rel="noopener noreferrer nofollow" className="mb-3 inline-flex items-center gap-1 text-sm text-primary hover:underline">
              Re-open employer form <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            </a>
          )}
          <div className="space-y-3">
            <Checkbox label="I have submitted this application on the employer's site" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
            <Field label="Note (optional)" hint="e.g. confirmation number">
              {(id, d) => <Input id={id} aria-describedby={d} value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />}
            </Field>
            <Button disabled={!confirmed} loading={confirm.isPending} onClick={() => confirm.mutate()}>
              Confirm submission
            </Button>
            <p className="text-xs text-subtle">Not submitted yet? Leave this page; the application stays here until you confirm.</p>
          </div>
        </Card>
      );
    case "withdrawn":
      return (
        <Card>
          <p className="text-sm">This application was withdrawn.</p>
        </Card>
      );
    default:
      return (
        <Card className="border-success/40">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-success" aria-hidden />
            <p className="text-sm">
              Submitted {formatDate(app.submitted_at, true)}. Track progress from the{" "}
              <Link to="/tracker" className="text-primary hover:underline">
                tracker
              </Link>
              .
            </p>
          </div>
        </Card>
      );
  }
}

function Preflight({ checks }: { checks: PreflightCheck[] }) {
  return (
    <ul className="space-y-2" aria-label="Pre-flight checks">
      {checks.map((c) => (
        <li key={c.name} className="flex items-start gap-2 text-sm">
          {c.ok ? (
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-label="passed" />
          ) : c.blocking ? (
            <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger" aria-label="blocking" />
          ) : (
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-label="warning" />
          )}
          <span>
            <span className="font-medium">{humanize(c.name)}:</span> {c.message}
          </span>
        </li>
      ))}
    </ul>
  );
}

function ApprovalPayload({ app }: { app: ApplicationDetail }) {
  const p = app.approval_payload as {
    job?: { title: string; company: string; url: string | null };
    resume?: { id: string } | null;
    cover_letter?: { id: string } | null;
    screening_answers?: { question: string; answer: string | null }[];
    adapter_level?: string;
  };
  return (
    <dl className="space-y-2 rounded border border-border p-3 text-sm">
      <div>
        <dt className="font-medium">Job</dt>
        <dd>
          {p.job?.title} — {p.job?.company} {p.job?.url && <span className="break-all text-subtle">({p.job.url})</span>}
        </dd>
      </div>
      <div>
        <dt className="font-medium">Documents</dt>
        <dd className="flex flex-wrap gap-3">
          {p.resume ? <Link className="text-primary hover:underline" to={`/documents/${p.resume.id}`}>Tailored resume</Link> : <span className="text-danger">No resume</span>}
          {p.cover_letter ? <Link className="text-primary hover:underline" to={`/documents/${p.cover_letter.id}`}>Cover letter</Link> : <span className="text-subtle">No cover letter</span>}
        </dd>
      </div>
      <div>
        <dt className="font-medium">Screening answers</dt>
        <dd>
          {p.screening_answers?.length ? (
            <ul className="list-disc pl-5">
              {p.screening_answers.map((a) => (
                <li key={a.question}>
                  {a.question} — <strong>{a.answer ?? "(unanswered)"}</strong>
                </li>
              ))}
            </ul>
          ) : (
            "None"
          )}
        </dd>
      </div>
      <div>
        <dt className="font-medium">Method</dt>
        <dd>{humanize(p.adapter_level ?? "manual_handoff")} — you submit on the employer's site</dd>
      </div>
    </dl>
  );
}

function DocumentsCard({ app }: { app: ApplicationDetail }) {
  const docs = useQuery({
    queryKey: ["documents", { job: app.job_id }],
    queryFn: () => api.get<DocumentSummary[]>("/api/documents", { job_id: app.job_id }),
  });
  const attached = [app.resume_doc_id, app.cover_letter_doc_id];
  const list = (docs.data ?? []).filter((d) => attached.includes(d.id));
  return (
    <Card>
      <CardTitle>Documents</CardTitle>
      {list.length === 0 ? (
        <p className="text-sm text-subtle">No documents attached yet.</p>
      ) : (
        <ul className="divide-y divide-border">
          {list.map((d) => (
            <li key={d.id} className="flex flex-wrap items-center gap-3 py-2">
              <FileText className="h-4 w-4 text-subtle" aria-hidden />
              <Link to={`/documents/${d.id}`} className="flex-1 font-medium hover:text-primary">
                {d.title}
              </Link>
              <Badge tone={d.grounded ? "success" : "danger"}>
                {d.grounded ? "Grounded" : `${d.grounding_report.failed} ungrounded`}
              </Badge>
              <span className="text-xs text-subtle">v{d.version}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function ScreeningCard({ app }: { app: ApplicationDetail }) {
  const [question, setQuestion] = useState("");
  const add = useAppMutation(app.id, () => api.post(`/api/applications/${app.id}/screening`, { question }));
  const locked = !["saved", "tailoring", "ready_for_review", "awaiting_approval", "approved", "handoff_opened", "awaiting_user_confirmation"].includes(app.status);
  return (
    <Card>
      <CardTitle>Screening questions</CardTitle>
      <p className="mb-3 text-sm text-subtle">
        Add the questions from the employer's form. JobPilot suggests answers only from verified facts. It never answers questions about work
        authorisation, salary, disability, demographics or criminal history.
      </p>
      {app.screening.length > 0 && (
        <ul className="mb-4 space-y-3">
          {app.screening.map((s) => (
            <ScreeningItem key={s.id} appId={app.id} item={s} locked={locked} />
          ))}
        </ul>
      )}
      {!locked && (
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (question.trim()) add.mutate(undefined, { onSuccess: () => setQuestion("") });
          }}
        >
          <Input aria-label="New screening question" placeholder="e.g. How many years of Python experience do you have?" value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={1000} />
          <Button type="submit" loading={add.isPending} disabled={!question.trim()}>
            Add
          </Button>
        </form>
      )}
    </Card>
  );
}

const CATEGORY: Record<string, { label: string; tone: "success" | "warning" | "danger" }> = {
  answerable_from_verified_facts: { label: "Answerable from your facts", tone: "success" },
  needs_user_input: { label: "Needs your input", tone: "warning" },
  sensitive_legal: { label: "Sensitive — you must answer", tone: "danger" },
};

function ScreeningItem({ appId, item, locked }: { appId: string; item: ScreeningAnswer; locked: boolean }) {
  const [value, setValue] = useState(item.answer ?? "");
  const save = useAppMutation(appId, (answer: string) => api.put(`/api/applications/${appId}/screening/${item.id}`, { answer }), "Answer saved");
  const cat = CATEGORY[item.category] ?? { label: humanize(item.category), tone: "warning" as const };
  return (
    <li className="rounded border border-border p-3 text-sm">
      <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <p className="font-medium">{item.question}</p>
        <Badge tone={cat.tone}>{cat.label}</Badge>
      </div>
      {item.suggested_answer && !item.answered_by_user && (
        <div className="mb-2 rounded bg-muted p-2">
          <p className="text-xs text-subtle">Suggested from {item.supporting_fact_ids.length} verified fact(s):</p>
          <p>{item.suggested_answer}</p>
          {!locked && (
            <Button size="sm" variant="ghost" className="mt-1" onClick={() => setValue(item.suggested_answer ?? "")}>
              Use suggestion
            </Button>
          )}
        </div>
      )}
      {locked ? (
        <p className="flex items-center gap-1">
          <Lock className="h-3.5 w-3.5 text-subtle" aria-hidden /> {item.answer ?? "(unanswered)"}
        </p>
      ) : (
        <div className="flex gap-2">
          <Textarea aria-label={`Your answer: ${item.question}`} className="min-h-[2.5rem]" value={value} onChange={(e) => setValue(e.target.value)} maxLength={4000} />
          <Button size="sm" variant="secondary" loading={save.isPending} disabled={!value.trim() || value === item.answer} onClick={() => save.mutate(value)}>
            Save
          </Button>
        </div>
      )}
    </li>
  );
}

function NotesCard({ app }: { app: ApplicationDetail }) {
  const [notes, setNotes] = useState(app.notes);
  const save = useAppMutation(app.id, () => api.patch(`/api/applications/${app.id}/notes`, { notes }, { headers: { "If-Match": `W/"${app.version}"` } }), "Notes saved");
  return (
    <Card>
      <CardTitle>Notes</CardTitle>
      <Textarea aria-label="Application notes" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={10000} />
      <Button size="sm" variant="secondary" className="mt-2" loading={save.isPending} disabled={notes === app.notes} onClick={() => save.mutate()}>
        Save notes
      </Button>
    </Card>
  );
}

function RemindersCard({ app }: { app: ApplicationDetail }) {
  const [due, setDue] = useState("");
  const [message, setMessage] = useState("Follow up on application");
  const add = useAppMutation(app.id, () => api.post(`/api/applications/${app.id}/reminders`, { due_at: new Date(due).toISOString(), message }), "Reminder added");
  const done = useAppMutation(app.id, (id: string) => api.post(`/api/reminders/${id}/done`));
  return (
    <Card>
      <CardTitle>
        <span className="inline-flex items-center gap-2">
          <Bell className="h-4 w-4" aria-hidden /> Reminders
        </span>
      </CardTitle>
      {app.reminders.length > 0 && (
        <ul className="mb-3 space-y-2 text-sm">
          {app.reminders.map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-2">
              <span className={cn(r.done && "text-subtle line-through")}>
                {r.message}
                <span className="block text-xs text-subtle">{formatDate(r.due_at, true)}</span>
              </span>
              {!r.done && (
                <Button size="sm" variant="ghost" onClick={() => done.mutate(r.id)}>
                  Done
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      <form
        className="space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (due && message.trim()) add.mutate(undefined, { onSuccess: () => setDue("") });
        }}
      >
        <Input type="datetime-local" aria-label="Reminder date and time" value={due} onChange={(e) => setDue(e.target.value)} />
        <Input aria-label="Reminder message" value={message} onChange={(e) => setMessage(e.target.value)} maxLength={500} />
        <Button type="submit" size="sm" variant="secondary" disabled={!due || !message.trim()} loading={add.isPending}>
          Add reminder
        </Button>
      </form>
    </Card>
  );
}

function ActivityCard({ app }: { app: ApplicationDetail }) {
  return (
    <Card>
      <CardTitle>History</CardTitle>
      <ol className="relative space-y-3 border-l border-border pl-4 text-sm">
        {[...app.activity].reverse().map((a) => (
          <li key={a.id}>
            <span className="absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full border border-border bg-surface" aria-hidden />
            <p>
              {a.to && a.from !== a.to ? (
                <>
                  {a.from ? `${statusLabel(a.from)} → ` : ""}
                  <strong>{statusLabel(a.to)}</strong>
                </>
              ) : (
                humanize(a.action)
              )}
            </p>
            <p className="text-xs text-subtle">
              {formatDate(a.at, true)} · by {a.actor}
            </p>
          </li>
        ))}
      </ol>
    </Card>
  );
}
