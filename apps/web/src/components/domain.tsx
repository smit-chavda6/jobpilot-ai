/** Domain widgets shared across pages: score breakdown, scam signals, fact review, re-auth dialog. */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, CheckCircle2, Flag, HelpCircle, Pencil, ShieldAlert, X, XCircle } from "lucide-react";
import { useState } from "react";
import { api, ApiError, errorMessage } from "@/api/client";
import type { Fact, FactStatus, MatchDetail, MatchSummary, ScamReport } from "@/api/types";
import { ACTION_LABEL, formatPercent, humanize, scoreTone } from "@/lib/format";
import { useToast } from "./Toast";
import { Badge, Button, Card, CardTitle, cn, Field, Input, Modal, ProgressBar, Select, Textarea } from "./ui";

export const FACT_CATEGORIES = ["experience", "project", "education", "skill", "certification", "achievement", "summary"];

export function ScorePill({ match }: { match: MatchSummary | null | undefined }) {
  if (!match) return <Badge>Not scored</Badge>;
  const tone = match.eligible ? scoreTone(match.score) : "danger";
  return (
    <span className="inline-flex items-center gap-1.5">
      <Badge tone={tone} className="tabular-nums">
        <span className="sr-only">Match score </span>
        {Math.round(match.score)}
      </Badge>
      <span className="text-xs text-subtle" title="Confidence reflects how much of the posting and your profile is known">
        conf. {formatPercent(match.confidence)}
      </span>
    </span>
  );
}

export function ActionBadge({ action }: { action: MatchSummary["recommended_action"] }) {
  const tone = action === "apply" ? "success" : action === "apply_after_tailoring" ? "primary" : action === "research_first" ? "warning" : "neutral";
  return <Badge tone={tone}>{ACTION_LABEL[action]}</Badge>;
}

export function ScoreBreakdown({ match, detail }: { match: MatchSummary; detail: MatchDetail }) {
  const comps = Object.entries(detail.breakdown.components);
  const exp = detail.explanation;
  return (
    <Card>
      <CardTitle action={<ActionBadge action={exp.recommended_action} />}>Why this score</CardTitle>
      <div className="mb-4 flex items-end gap-4">
        <div>
          <div className="text-4xl font-bold tabular-nums">{Math.round(match.score)}</div>
          <div className="text-xs text-subtle">out of 100</div>
        </div>
        <div className="text-sm">
          <div>
            Confidence: <strong>{formatPercent(match.confidence)}</strong>
          </div>
          {!match.eligible && <div className="text-danger">A hard filter failed — score is capped.</div>}
        </div>
      </div>
      <ul className="space-y-3" aria-label="Score components">
        {comps.map(([name, c]) => (
          <li key={name}>
            <div className="mb-1 flex justify-between text-sm">
              <span className="font-medium">
                {humanize(name)} <span className="text-subtle">({Math.round(c.weight * 100)}%)</span>
                {c.status !== "known" && (
                  <Badge tone="warning" className="ml-2">
                    {c.status}
                  </Badge>
                )}
              </span>
              <span className="tabular-nums">+{c.contribution.toFixed(1)}</span>
            </div>
            <ProgressBar value={(c.value ?? 0) * 100} label={`${name} component`} tone={c.status === "known" ? "primary" : "warning"} />
            <p className="mt-1 text-xs text-subtle">{c.detail}</p>
          </li>
        ))}
      </ul>
      {detail.breakdown.filters.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-1 text-sm font-semibold">Hard filters</h3>
          <ul className="space-y-1 text-sm">
            {detail.breakdown.filters.map((f) => (
              <li key={f.name} className="flex gap-2">
                {f.passed ? <CheckCircle2 className="h-4 w-4 text-success" aria-label="passed" /> : <XCircle className="h-4 w-4 text-danger" aria-label="failed" />}
                {f.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <ExplainList title="Fit reasons" items={exp.fit_reasons} icon={<Check className="h-4 w-4 text-success" aria-hidden />} />
        <ExplainList title="Missing or uncertain" items={exp.missing_or_uncertain} icon={<HelpCircle className="h-4 w-4 text-warning" aria-hidden />} />
        <ExplainList title="Questions to investigate" items={exp.questions_to_investigate} icon={<HelpCircle className="h-4 w-4 text-info" aria-hidden />} />
        <div>
          <h3 className="mb-1 text-sm font-semibold">Matched skills</h3>
          <div className="flex flex-wrap gap-1">
            {exp.matched_skills.length ? exp.matched_skills.map((s) => <Badge key={s} tone="success">{s}</Badge>) : <span className="text-sm text-subtle">None</span>}
          </div>
        </div>
      </div>
      {detail.highlight_facts.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-1 text-sm font-semibold">Verified experience to highlight</h3>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {detail.highlight_facts.map((f) => (
              <li key={f.id}>{f.text}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="mt-4 text-xs text-subtle">
        Scored {new Date(detail.scored_at).toLocaleString()} with config {String(detail.config_snapshot.version ?? "")}.
      </p>
    </Card>
  );
}

function ExplainList({ title, items, icon }: { title: string; items: string[]; icon: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-1 text-sm font-semibold">{title}</h3>
      {items.length ? (
        <ul className="space-y-1 text-sm">
          {items.map((t) => (
            <li key={t} className="flex gap-2">
              <span className="mt-0.5 shrink-0">{icon}</span>
              {t}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-subtle">None</p>
      )}
    </div>
  );
}

const SCAM_TONE = { none: "success", low: "info", medium: "warning", high: "danger" } as const;

export function ScamPanel({ report, jobId }: { report: ScamReport; jobId?: string }) {
  const toast = useToast();
  const [reported, setReported] = useState<Set<string>>(new Set());
  const feedback = useMutation({
    mutationFn: (code: string) => api.post(`/api/jobs/${jobId}/scam-feedback`, { signal_code: code, comment: "" }),
    onSuccess: (_d, code) => {
      setReported((s) => new Set(s).add(code));
      toast.success("Thanks — reported as a false positive.");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card className={cn(report.level === "high" && "border-danger/50")}>
      <CardTitle action={<Badge tone={SCAM_TONE[report.level]}>{report.level === "none" ? "No signals" : `${report.level} signals`}</Badge>}>
        <span className="inline-flex items-center gap-2">
          <ShieldAlert className="h-4 w-4" aria-hidden /> Quality & scam signals
        </span>
      </CardTitle>
      <p className="text-sm">{report.summary}</p>
      {report.signals.length > 0 && (
        <ul className="mt-3 space-y-3">
          {report.signals.map((s) => (
            <li key={s.code} className="rounded border border-border p-3 text-sm">
              <div className="flex items-start justify-between gap-2">
                <span className="flex items-center gap-2 font-medium">
                  <AlertTriangle className="h-4 w-4 text-warning" aria-hidden />
                  {s.message}
                </span>
                <Badge tone={s.severity === "high" ? "danger" : s.severity === "medium" ? "warning" : "info"}>{s.severity}</Badge>
              </div>
              {s.evidence && <blockquote className="mt-2 border-l-2 border-border pl-2 text-xs text-subtle">“{s.evidence}”</blockquote>}
              {jobId && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="mt-2"
                  icon={<Flag className="h-3.5 w-3.5" aria-hidden />}
                  disabled={reported.has(s.code)}
                  onClick={() => feedback.mutate(s.code)}
                >
                  {reported.has(s.code) ? "Reported" : "Report false positive"}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-subtle">
        Signals are heuristics{report.signals.length > 0 && ` (${formatPercent(report.confidence)} confidence)`}. They never mean a company is
        fraudulent.
      </p>
    </Card>
  );
}

/** Lists facts with confirm / reject / edit controls. Used by onboarding and the profile page. */
export function FactReview({ facts, compact = false }: { facts: Fact[]; compact?: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [editing, setEditing] = useState<Fact | null>(null);
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["facts"] });
    void qc.invalidateQueries({ queryKey: ["dashboard"] });
  };
  const setStatus = useMutation({
    mutationFn: ({ ids, status }: { ids: string[]; status: FactStatus }) => api.post("/api/facts/status", { fact_ids: ids, status }),
    onSuccess: invalidate,
    onError: (e) => toast.error(errorMessage(e)),
  });
  const del = useMutation({
    mutationFn: (id: string) => api.del(`/api/facts/${id}`),
    onSuccess: invalidate,
    onError: (e) => toast.error(errorMessage(e)),
  });
  const candidates = facts.filter((f) => f.status === "candidate");
  const grouped = FACT_CATEGORIES.map((c) => [c, facts.filter((f) => f.category === c)] as const).filter(([, fs]) => fs.length);

  return (
    <div className="space-y-4">
      {candidates.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-warning/40 bg-warning/5 p-3 text-sm">
          <span>
            <strong>{candidates.length}</strong> unconfirmed fact{candidates.length === 1 ? "" : "s"}. Unconfirmed facts are never used in matching or generated documents.
          </span>
          <Button size="sm" loading={setStatus.isPending} onClick={() => setStatus.mutate({ ids: candidates.map((f) => f.id), status: "confirmed" })}>
            Confirm all {candidates.length}
          </Button>
        </div>
      )}
      {grouped.map(([cat, fs]) => (
        <section key={cat} aria-label={humanize(cat)}>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-subtle">{humanize(cat)}</h3>
          <ul className="space-y-2">
            {fs.map((f) => (
              <li
                key={f.id}
                className={cn(
                  "flex flex-wrap items-start gap-3 rounded border p-3 text-sm",
                  f.status === "confirmed" ? "border-success/30" : f.status === "rejected" ? "border-border opacity-60" : "border-warning/40",
                )}
              >
                <div className="min-w-0 flex-1">
                  <p className={cn(f.status === "rejected" && "line-through")}>{f.text}</p>
                  {!compact && <FactAttributes attributes={f.attributes} />}
                </div>
                <Badge tone={f.status === "confirmed" ? "success" : f.status === "rejected" ? "neutral" : "warning"}>{f.status}</Badge>
                <div className="flex gap-1">
                  {f.status !== "confirmed" && (
                    <Button size="sm" variant="secondary" aria-label={`Confirm: ${f.text}`} onClick={() => setStatus.mutate({ ids: [f.id], status: "confirmed" })}>
                      <Check className="h-4 w-4" aria-hidden />
                    </Button>
                  )}
                  {f.status !== "rejected" && (
                    <Button size="sm" variant="ghost" aria-label={`Reject: ${f.text}`} onClick={() => setStatus.mutate({ ids: [f.id], status: "rejected" })}>
                      <X className="h-4 w-4" aria-hidden />
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" aria-label={`Edit: ${f.text}`} onClick={() => setEditing(f)}>
                    <Pencil className="h-4 w-4" aria-hidden />
                  </Button>
                  {f.status === "rejected" && (
                    <Button size="sm" variant="ghost" onClick={() => del.mutate(f.id)}>
                      Delete
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
      <FactEditor fact={editing} onClose={() => setEditing(null)} />
    </div>
  );
}

function FactAttributes({ attributes }: { attributes: Record<string, unknown> }) {
  const entries = Object.entries(attributes).filter(([, v]) => v !== null && v !== "" && !(Array.isArray(v) && v.length === 0));
  if (!entries.length) return null;
  return (
    <dl className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-subtle">
      {entries.map(([k, v]) => (
        <div key={k}>
          <dt className="inline">{humanize(k)}: </dt>
          <dd className="inline">{Array.isArray(v) ? v.join(", ") : String(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Create (fact === "new") or edit a fact. Facts written or edited by the user are confirmed by the server. */
export function FactEditor({ fact, onClose }: { fact: Fact | "new" | null; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const isNew = fact === "new";
  const [text, setText] = useState("");
  const [category, setCategory] = useState("experience");
  const [lastKey, setLastKey] = useState<string | null>(null);
  const key = fact === null ? null : isNew ? "new" : fact.id;
  if (key !== lastKey) {
    setLastKey(key);
    setText(fact && fact !== "new" ? fact.text : "");
    setCategory(fact && fact !== "new" ? fact.category : "experience");
  }
  const save = useMutation({
    mutationFn: () =>
      isNew ? api.post("/api/facts", { category, text }) : api.patch(`/api/facts/${(fact as Fact).id}`, { category, text }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["facts"] });
      toast.success(isNew ? "Fact added" : "Fact updated");
      onClose();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Modal
      open={fact !== null}
      title={isNew ? "Add a fact" : "Edit fact"}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={save.isPending} disabled={text.trim().length < 3} onClick={() => save.mutate()}>
            Save
          </Button>
        </>
      }
    >
      <p className="text-subtle">
        Write one atomic, truthful claim, e.g. “Built a churn model with XGBoost at Acme, 2022–2024”. Saving confirms the fact, because it is your own statement.
      </p>
      <Field label="Category">
        {(id) => (
          <Select id={id} value={category} onChange={(e) => setCategory(e.target.value)}>
            {FACT_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {humanize(c)}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Fact">
        {(id) => <Textarea id={id} value={text} onChange={(e) => setText(e.target.value)} maxLength={1000} />}
      </Field>
    </Modal>
  );
}

/** Password re-entry required by the API (reauth_required) before export, deletion and integration changes. */
export function ReauthDialog({ open, onClose, onDone, reason }: { open: boolean; onClose: () => void; onDone: () => void; reason: string }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const reauth = useMutation({
    mutationFn: () => api.post("/api/auth/reauth", { password }),
    onSuccess: () => {
      setPassword("");
      setError(null);
      onDone();
    },
    onError: (e) => setError(e instanceof ApiError && e.status === 401 ? "Incorrect password" : errorMessage(e)),
  });
  return (
    <Modal
      open={open}
      title="Confirm it's you"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={reauth.isPending} disabled={!password} onClick={() => reauth.mutate()}>
            Continue
          </Button>
        </>
      }
    >
      <p>{reason}</p>
      <Field label="Password" error={error ?? undefined}>
        {(id, d) => (
          <Input
            id={id}
            type="password"
            autoComplete="current-password"
            aria-describedby={d}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && password && reauth.mutate()}
          />
        )}
      </Field>
    </Modal>
  );
}
