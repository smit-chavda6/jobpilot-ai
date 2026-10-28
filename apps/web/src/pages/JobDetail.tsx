import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, RefreshCw, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, ApiError, errorMessage, newIdempotencyKey } from "@/api/client";
import type { ApplicationSummary, JobDetail as Job } from "@/api/types";
import { ScamPanel, ScoreBreakdown } from "@/components/domain";
import { useToast } from "@/components/Toast";
import { Badge, Button, Card, CardTitle, DemoBadge, QueryView } from "@/components/ui";
import { formatDate, formatSalary, humanize } from "@/lib/format";

export default function JobDetail() {
  const { jobId = "" } = useParams();
  const q = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.get<Job>(`/api/jobs/${jobId}`),
    // With a separate worker (Docker Compose), scoring finishes a moment after import: poll until it lands.
    refetchInterval: (query) => (query.state.data && !query.state.data.match && query.state.dataUpdateCount < 40 ? 3000 : false),
  });
  return (
    <>
      <Link to="/jobs" className="mb-4 inline-flex items-center gap-1 text-sm text-subtle hover:text-fg">
        <ArrowLeft className="h-4 w-4" aria-hidden /> Back to jobs
      </Link>
      <QueryView query={q} loadingLabel="Loading job">
        {(job) => <JobView job={job} />}
      </QueryView>
    </>
  );
}

function JobView({ job }: { job: Job }) {
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const [key] = useState(newIdempotencyKey);
  const start = useMutation({
    mutationFn: () => api.post<ApplicationSummary>("/api/applications", { job_id: job.id }, { idempotencyKey: key }),
    onSuccess: (a) => {
      void qc.invalidateQueries({ queryKey: ["applications"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
      navigate(`/applications/${a.id}`);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === "duplicate_application") toast.error("You already have an application for this job.");
      else toast.error(errorMessage(e));
    },
  });
  const reverify = useMutation({
    mutationFn: () => api.post<{ verification_status: string }>(`/api/jobs/${job.id}/reverify`),
    onSuccess: (r) => {
      toast.show(`Listing status: ${humanize(r.verification_status)}`);
      void qc.invalidateQueries({ queryKey: ["job", job.id] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const salary = formatSalary(job.salary_min, job.salary_max, job.salary_currency);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">
            {job.title} {job.is_demo && <DemoBadge />}
          </h1>
          <p className="text-subtle">
            {job.company}
            {job.location && ` · ${job.location}`}
            {job.remote_policy !== "unknown" && ` · ${humanize(job.remote_policy)}`}
            {job.employment_type !== "unknown" && ` · ${humanize(job.employment_type)}`}
            {salary && ` · ${salary}`}
          </p>
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            <Badge>Source: {humanize(job.source)}</Badge>
            <Badge tone={job.verification_status === "verified_live" ? "success" : job.verification_status === "expired" || job.verification_status === "unavailable" ? "danger" : "neutral"}>
              {humanize(job.verification_status)}
            </Badge>
            <Badge>Imported {formatDate(job.created_at)}</Badge>
            {job.duplicate_of && (
              <Badge tone="warning">
                Possible duplicate of{" "}
                <Link className="underline" to={`/jobs/${job.duplicate_of.id}`}>
                  {job.duplicate_of.title} ({humanize(job.duplicate_of.source)})
                </Link>
              </Badge>
            )}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {job.url && (
            <a href={job.url} target="_blank" rel="noopener noreferrer nofollow">
              <Button variant="secondary" icon={<ExternalLink className="h-4 w-4" aria-hidden />}>
                Original posting
              </Button>
            </a>
          )}
          {job.url && (
            <Button variant="secondary" icon={<RefreshCw className="h-4 w-4" aria-hidden />} loading={reverify.isPending} onClick={() => reverify.mutate()}>
              Check if still open
            </Button>
          )}
          {job.application_id ? (
            <Link to={`/applications/${job.application_id}`}>
              <Button>Open application</Button>
            </Link>
          ) : (
            <Button icon={<Sparkles className="h-4 w-4" aria-hidden />} loading={start.isPending} onClick={() => start.mutate()}>
              Tailor & prepare application
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-6 lg:col-span-3">
          {job.match && job.match_detail ? (
            <ScoreBreakdown match={job.match} detail={job.match_detail} />
          ) : (
            <Card>
              <p role="status" className="text-sm text-subtle">
                Scoring in progress… If this doesn't update, confirm some facts in your profile and use Re-score on the Jobs page.
              </p>
            </Card>
          )}
          <Card>
            <CardTitle>Description</CardTitle>
            {/* description_html is sanitised server-side with an allowlist (nh3); links get rel=noopener. */}
            <div className="prose-job text-sm" dangerouslySetInnerHTML={{ __html: job.description_html }} />
          </Card>
        </div>
        <div className="space-y-6 lg:col-span-2">
          <ScamPanel report={job.scam_report} jobId={job.id} />
          <Card>
            <CardTitle>Requirements</CardTitle>
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="font-medium">Required skills</dt>
                <dd className="mt-1 flex flex-wrap gap-1">{job.required_skills.length ? job.required_skills.map((s) => <Badge key={s}>{s}</Badge>) : <span className="text-subtle">Not stated</span>}</dd>
              </div>
              <div>
                <dt className="font-medium">Preferred skills</dt>
                <dd className="mt-1 flex flex-wrap gap-1">{job.preferred_skills.length ? job.preferred_skills.map((s) => <Badge key={s}>{s}</Badge>) : <span className="text-subtle">Not stated</span>}</dd>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <dt className="font-medium">Experience</dt>
                  <dd className="text-subtle">{job.min_years != null ? `${job.min_years}+ years` : "Unknown"}</dd>
                </div>
                <div>
                  <dt className="font-medium">Education</dt>
                  <dd className="text-subtle">{job.education_req ? humanize(job.education_req) : "Unknown"}</dd>
                </div>
                <div>
                  <dt className="font-medium">Visa sponsorship</dt>
                  <dd className="text-subtle">{humanize(job.sponsorship)}</dd>
                </div>
                <div>
                  <dt className="font-medium">Last seen</dt>
                  <dd className="text-subtle">{formatDate(job.last_seen_at)}</dd>
                </div>
              </div>
            </dl>
          </Card>
        </div>
      </div>
    </div>
  );
}
