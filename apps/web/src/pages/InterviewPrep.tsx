import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, Sparkles } from "lucide-react";
import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errorMessage } from "@/api/client";
import type { BankQuestion, JobSummary, Page, PrepSession, Star } from "@/api/types";
import { useToast } from "@/components/Toast";
import { Badge, Button, Card, CardTitle, cn, EmptyState, PageHeader, ProgressBar, QueryView, Select, Spinner, Textarea } from "@/components/ui";
import { formatDate, humanize } from "@/lib/format";

export default function InterviewPrep() {
  const [jobId, setJobId] = useState("");
  const [active, setActive] = useState<string | null>(null);
  const jobs = useQuery({ queryKey: ["jobs", "prep-picker"], queryFn: () => api.get<Page<JobSummary>>("/api/jobs", { limit: 100 }) });
  return (
    <>
      <PageHeader
        title="Interview Prep"
        description="Practice questions, STAR scaffolds built only from your confirmed facts, and mock sessions scored on relevance, structure, specificity and clarity."
      />
      <Card className="mb-6">
        <label className="mb-1 block text-sm font-medium" htmlFor="prep-job">
          Prepare for a specific job (optional)
        </label>
        <Select id="prep-job" value={jobId} onChange={(e) => setJobId(e.target.value)} className="max-w-md">
          <option value="">General preparation</option>
          {jobs.data?.items.map((j) => (
            <option key={j.id} value={j.id}>
              {j.title} — {j.company}
            </option>
          ))}
        </Select>
      </Card>
      {active ? (
        <SessionRunner id={active} onClose={() => setActive(null)} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <QuestionBank jobId={jobId} />
          <div className="space-y-6">
            <Sessions jobId={jobId} onOpen={setActive} />
          </div>
        </div>
      )}
    </>
  );
}

function QuestionBank({ jobId }: { jobId: string }) {
  const bank = useQuery({ queryKey: ["prep-bank", jobId], queryFn: () => api.get<Record<string, BankQuestion[]>>("/api/interview-prep/bank", { job_id: jobId }) });
  const [star, setStar] = useState<Star | null>(null);
  const toast = useToast();
  const scaffold = useMutation({
    mutationFn: (question: string) => api.post<Star>("/api/interview-prep/star", { question, job_id: jobId || null }),
    onSuccess: setStar,
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card>
      <CardTitle>Question bank</CardTitle>
      <QueryView query={bank}>
        {(b) => (
          <div className="space-y-4">
            {Object.entries(b).map(([type, qs]) => (
              <section key={type}>
                <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-subtle">{humanize(type)}</h3>
                <ul className="space-y-1">
                  {qs.map((q) => (
                    <li key={q.question} className="flex items-start justify-between gap-2 rounded p-1.5 text-sm hover:bg-muted">
                      <span>
                        {q.question}
                        {q.skills.length > 0 && <span className="ml-1 text-xs text-subtle">({q.skills.join(", ")})</span>}
                      </span>
                      <Button size="sm" variant="ghost" icon={<Sparkles className="h-3.5 w-3.5" aria-hidden />} onClick={() => scaffold.mutate(q.question)} aria-label={`STAR scaffold for: ${q.question}`}>
                        STAR
                      </Button>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        )}
      </QueryView>
      {scaffold.isPending && <Spinner label="Building scaffold" />}
      {star && (
        <div className="mt-4 rounded border border-primary/40 bg-primary/5 p-3 text-sm" role="region" aria-label="STAR scaffold">
          <p className="mb-2 font-medium">{star.question}</p>
          {star.note ? (
            <p className="text-subtle">{star.note}</p>
          ) : (
            <dl className="space-y-1">
              {(["situation", "task", "action", "result"] as const).map((k) => (
                <div key={k}>
                  <dt className="inline font-semibold">{humanize(k)}: </dt>
                  <dd className={cn("inline", star[k]?.startsWith("[") && "italic text-subtle")}>{star[k]}</dd>
                </div>
              ))}
            </dl>
          )}
          <p className="mt-2 text-xs text-subtle">Built from {star.supporting_fact_ids.length} confirmed fact(s). Placeholders in [brackets] are details your facts don't state — fill them in truthfully.</p>
        </div>
      )}
    </Card>
  );
}

function Sessions({ jobId, onOpen }: { jobId: string; onOpen: (id: string) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const sessions = useQuery({ queryKey: ["prep-sessions"], queryFn: () => api.get<PrepSession[]>("/api/interview-prep/sessions") });
  const start = useMutation({
    mutationFn: () => api.post<PrepSession>("/api/interview-prep/sessions", { job_id: jobId || null, questions: 5 }),
    onSuccess: (s) => {
      void qc.invalidateQueries({ queryKey: ["prep-sessions"] });
      onOpen(s.id);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const completed = (sessions.data ?? []).filter((s) => s.overall_score !== null).sort((a, b) => a.created_at.localeCompare(b.created_at));
  return (
    <>
      <Card>
        <CardTitle action={<Button size="sm" icon={<Play className="h-4 w-4" aria-hidden />} loading={start.isPending} onClick={() => start.mutate()}>Start mock interview</Button>}>
          Mock interviews
        </CardTitle>
        <QueryView query={sessions} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No sessions yet">Start a 5-question mock interview. Answers are scored with a transparent rubric, not by a hidden model.</EmptyState>}>
          {(list) => (
            <ul className="divide-y divide-border text-sm">
              {list.map((s) => (
                <li key={s.id} className="flex items-center justify-between gap-2 py-2">
                  <span>
                    {formatDate(s.created_at, true)} · {s.questions.length} questions
                    {s.completed && <Badge tone="success" className="ml-2">completed</Badge>}
                  </span>
                  <span className="flex items-center gap-2">
                    {s.overall_score !== null && <Badge tone="primary">{s.overall_score}/5</Badge>}
                    <Button size="sm" variant="secondary" onClick={() => onOpen(s.id)}>
                      {s.completed ? "Review" : "Continue"}
                    </Button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </QueryView>
      </Card>
      <Card>
        <CardTitle>Progress</CardTitle>
        {completed.length < 2 ? (
          <p className="text-sm text-subtle">Complete at least two sessions to see a trend (n = {completed.length}).</p>
        ) : (
          <div className="h-48" role="img" aria-label={`Overall score over ${completed.length} sessions`}>
            <ResponsiveContainer>
              <LineChart data={completed.map((s, i) => ({ n: i + 1, score: s.overall_score }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--border))" />
                <XAxis dataKey="n" stroke="rgb(var(--subtle))" fontSize={12} />
                <YAxis domain={[0, 5]} stroke="rgb(var(--subtle))" fontSize={12} />
                <Tooltip />
                <Line type="monotone" dataKey="score" stroke="rgb(var(--primary))" strokeWidth={2} dot />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>
    </>
  );
}

function SessionRunner({ id, onClose }: { id: string; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const s = useQuery({ queryKey: ["prep-session", id], queryFn: () => api.get<PrepSession>(`/api/interview-prep/sessions/${id}`) });
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const answer = useMutation({
    mutationFn: ({ qid, text }: { qid: string; text: string }) => api.post<PrepSession>(`/api/interview-prep/sessions/${id}/answers`, { question_id: qid, answer: text }),
    onSuccess: (d) => {
      qc.setQueryData(["prep-session", id], d);
      void qc.invalidateQueries({ queryKey: ["prep-sessions"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card>
      <CardTitle action={<Button variant="secondary" size="sm" onClick={onClose}>Back</Button>}>Mock interview</CardTitle>
      <QueryView query={s}>
        {(sess) => (
          <ol className="space-y-6">
            {sess.questions.map((q, i) => {
              const fb = sess.feedback[q.id];
              return (
                <li key={q.id}>
                  <p className="mb-2 font-medium">
                    {i + 1}. {q.question} <Badge className="ml-1">{q.type}</Badge>
                  </p>
                  <Textarea
                    aria-label={`Your answer to question ${i + 1}`}
                    value={drafts[q.id] ?? sess.answers[q.id] ?? ""}
                    onChange={(e) => setDrafts((d) => ({ ...d, [q.id]: e.target.value }))}
                    placeholder="Answer as you would out loud. Aim for 90–200 words."
                  />
                  <Button size="sm" className="mt-2" loading={answer.isPending && answer.variables?.qid === q.id} disabled={!(drafts[q.id] ?? "").trim()} onClick={() => answer.mutate({ qid: q.id, text: drafts[q.id] ?? "" })}>
                    {fb ? "Re-score" : "Get feedback"}
                  </Button>
                  {fb && (
                    <div className="mt-3 rounded border border-border p-3 text-sm">
                      <p className="mb-2 font-medium">Overall {fb.overall}/5 · {fb.word_count} words</p>
                      <div className="grid gap-2 sm:grid-cols-4">
                        {Object.entries(fb.scores).map(([k, v]) => (
                          <div key={k}>
                            <div className="flex justify-between text-xs">
                              <span>{humanize(k)}</span>
                              <span>{v}/5</span>
                            </div>
                            <ProgressBar value={(v / 5) * 100} label={`${k} score`} tone={v >= 4 ? "success" : v >= 3 ? "warning" : "danger"} />
                          </div>
                        ))}
                      </div>
                      {fb.tips.length > 0 && (
                        <ul className="mt-2 list-disc pl-5 text-subtle">
                          {fb.tips.map((t) => (
                            <li key={t}>{t}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </QueryView>
    </Card>
  );
}
