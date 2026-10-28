import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Bell, Briefcase, CheckCircle2, FileQuestion, Inbox } from "lucide-react";
import { Link } from "react-router";
import { api } from "@/api/client";
import type { Dashboard as DashboardData } from "@/api/types";
import { ActionBadge } from "@/components/domain";
import { Badge, Button, Card, CardTitle, DemoBadge, EmptyState, PageHeader, QueryView } from "@/components/ui";
import { formatDate, scoreTone, statusLabel } from "@/lib/format";

export default function Dashboard() {
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<DashboardData>("/api/dashboard") });
  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Your search at a glance. Everything here is computed from records you created or imported."
        actions={
          <Link to="/jobs?import=1">
            <Button icon={<Briefcase className="h-4 w-4" aria-hidden />}>Import jobs</Button>
          </Link>
        }
      />
      <QueryView query={q}>
        {(d) => (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <Stat label="Jobs tracked" value={d.counts.jobs} to="/jobs" icon={<Briefcase className="h-4 w-4" aria-hidden />} />
              <Stat label="Applications" value={d.counts.applications} to="/tracker" icon={<CheckCircle2 className="h-4 w-4" aria-hidden />} />
              <Stat
                label="Facts to confirm"
                value={d.counts.candidate_facts}
                to="/profile"
                icon={<FileQuestion className="h-4 w-4" aria-hidden />}
                hint={`${d.counts.confirmed_facts} confirmed`}
              />
              <Stat label="Emails to review" value={d.counts.pending_triage} to="/inbox" icon={<Inbox className="h-4 w-4" aria-hidden />} />
            </div>

            <div className="grid gap-6 lg:grid-cols-3">
              <Card className="lg:col-span-2">
                <CardTitle action={<Link className="text-sm text-primary hover:underline" to="/jobs">All jobs</Link>}>Top matches</CardTitle>
                {d.top_matches.length === 0 ? (
                  <EmptyState
                    title="No scored jobs yet"
                    action={
                      <Link to="/jobs?import=1">
                        <Button size="sm">Import your first job</Button>
                      </Link>
                    }
                  >
                    Paste a job description, import a CSV, upload a job-alert email or pull from a public job board.
                  </EmptyState>
                ) : (
                  <ul className="divide-y divide-border">
                    {d.top_matches.map((m) => (
                      <li key={m.id}>
                        <Link to={`/jobs/${m.id}`} className="flex items-center gap-3 py-3 hover:bg-muted/50">
                          <Badge tone={scoreTone(m.score)} className="w-10 justify-center tabular-nums">
                            {Math.round(m.score)}
                          </Badge>
                          <div className="min-w-0 flex-1">
                            <p className="truncate font-medium">
                              {m.title} {m.is_demo && <DemoBadge />}
                            </p>
                            <p className="truncate text-sm text-subtle">{m.company}</p>
                          </div>
                          <ActionBadge action={m.recommended_action} />
                          <ArrowRight className="h-4 w-4 text-subtle" aria-hidden />
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>

              <div className="space-y-6">
                <Card>
                  <CardTitle action={<Link className="text-sm text-primary hover:underline" to="/tracker">Tracker</Link>}>Pipeline</CardTitle>
                  {Object.keys(d.applications_by_status).length === 0 ? (
                    <p className="text-sm text-subtle">No applications yet.</p>
                  ) : (
                    <ul className="space-y-1 text-sm">
                      {Object.entries(d.applications_by_status).map(([s, n]) => (
                        <li key={s} className="flex justify-between">
                          <span>{statusLabel(s)}</span>
                          <span className="tabular-nums font-medium">{n}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </Card>
                <Card>
                  <CardTitle>
                    <span className="inline-flex items-center gap-2">
                      <Bell className="h-4 w-4" aria-hidden /> Upcoming reminders
                    </span>
                  </CardTitle>
                  {d.upcoming_reminders.length === 0 ? (
                    <p className="text-sm text-subtle">Nothing scheduled.</p>
                  ) : (
                    <ul className="space-y-2 text-sm">
                      {d.upcoming_reminders.map((r) => (
                        <li key={r.id}>
                          <p>{r.message}</p>
                          <p className="text-xs text-subtle">{formatDate(r.due_at, true)}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </Card>
              </div>
            </div>
          </div>
        )}
      </QueryView>
    </>
  );
}

function Stat({ label, value, to, icon, hint }: { label: string; value: number; to: string; icon: React.ReactNode; hint?: string }) {
  return (
    <Link to={to} className="block">
      <Card className="h-full hover:border-primary/50">
        <div className="flex items-center gap-2 text-sm text-subtle">
          {icon} {label}
        </div>
        <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
        {hint && <div className="text-xs text-subtle">{hint}</div>}
      </Card>
    </Link>
  );
}
