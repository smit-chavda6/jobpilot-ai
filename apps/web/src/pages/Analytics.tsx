import { useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/api/client";
import type { Analytics as Data, Rate } from "@/api/types";
import { Card, CardTitle, Checkbox, PageHeader, QueryView } from "@/components/ui";
import { formatPercent, humanize, statusLabel } from "@/lib/format";

const axis = { stroke: "rgb(var(--subtle))", fontSize: 12 };
const grid = <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--border))" />;

export default function Analytics() {
  const [includeDemo, setIncludeDemo] = useState(false);
  const q = useQuery({ queryKey: ["analytics", includeDemo], queryFn: () => api.get<Data>("/api/analytics", { include_demo: includeDemo }) });
  return (
    <>
      <PageHeader
        title="Analytics"
        description="Computed with SQL from your stored applications. Rates show n and a 95% Wilson interval, and are hidden below the minimum sample size."
        actions={<Checkbox label="Include DEMO data" checked={includeDemo} onChange={(e) => setIncludeDemo(e.target.checked)} />}
      />
      <QueryView query={q}>
        {(d) => (
          <div className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-3">
              <RateCard title="Response rate" rate={d.response_rate} />
              <RateCard title="Interview rate" rate={d.interview_rate} />
              <RateCard title="Offer rate" rate={d.offer_rate} />
            </div>
            <div className="grid gap-6 lg:grid-cols-2">
              <Card>
                <CardTitle>Funnel</CardTitle>
                <ChartFrame label="Application funnel" n={d.funnel[0]?.count ?? 0}>
                  <BarChart data={d.funnel} layout="vertical" margin={{ left: 40 }}>
                    {grid}
                    <XAxis type="number" allowDecimals={false} {...axis} />
                    <YAxis type="category" dataKey="stage" width={110} {...axis} />
                    <Tooltip formatter={(v: number, _n, p) => [`${v}${p.payload.drop_off != null ? ` (−${formatPercent(p.payload.drop_off)} from previous)` : ""}`, "Count"]} />
                    <Bar dataKey="count" fill="rgb(var(--primary))" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ChartFrame>
              </Card>
              <Card>
                <CardTitle>Time to first response</CardTitle>
                <p className="mb-2 text-sm text-subtle">
                  n = {d.time_to_response.n}
                  {d.time_to_response.median_days != null && ` · median ${d.time_to_response.median_days} days`}
                </p>
                <ChartFrame label="Time to response distribution" n={d.time_to_response.n}>
                  <BarChart data={d.time_to_response.buckets}>
                    {grid}
                    <XAxis dataKey="bucket" {...axis} />
                    <YAxis allowDecimals={false} {...axis} />
                    <Tooltip />
                    <Bar dataKey="count" fill="rgb(var(--info))" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ChartFrame>
              </Card>
              <Card>
                <CardTitle>Weekly submissions</CardTitle>
                <ChartFrame label="Submissions per week" n={d.weekly_submissions.reduce((a, b) => a + b.count, 0)}>
                  <BarChart data={d.weekly_submissions}>
                    {grid}
                    <XAxis dataKey="week" {...axis} />
                    <YAxis allowDecimals={false} {...axis} />
                    <Tooltip />
                    <Bar dataKey="count" fill="rgb(var(--success))" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ChartFrame>
              </Card>
              <Card>
                <CardTitle>Applications by status</CardTitle>
                {Object.keys(d.by_status).length === 0 ? (
                  <p className="text-sm text-subtle">No applications.</p>
                ) : (
                  <table className="w-full text-sm">
                    <tbody className="divide-y divide-border">
                      {Object.entries(d.by_status).map(([s, n]) => (
                        <tr key={s}>
                          <th scope="row" className="py-1.5 text-left font-normal">
                            {statusLabel(s)}
                          </th>
                          <td className="py-1.5 text-right tabular-nums">{n}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Card>
              <Card>
                <CardTitle>Response rate by source</CardTitle>
                <RateTable rows={d.by_source.map((r) => ({ label: humanize(r.source), rate: r.response_rate }))} />
              </Card>
              <Card>
                <CardTitle>Match score vs interview rate</CardTitle>
                <RateTable rows={d.score_band_vs_interview.map((r) => ({ label: `Score ${r.band}`, rate: r.interview_rate }))} />
              </Card>
            </div>
            <p className="flex items-start gap-2 rounded border border-border bg-muted/50 p-3 text-sm text-subtle">
              <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {d.note}
            </p>
            <p className="text-xs text-subtle">
              Totals: {d.totals.jobs} jobs · {d.totals.applications} applications · {d.totals.submitted} submitted
              {d.totals.demo_applications > 0 && ` · ${d.totals.demo_applications} DEMO applications ${d.totals.include_demo ? "included" : "excluded"}`}
            </p>
          </div>
        )}
      </QueryView>
    </>
  );
}

function RateCard({ title, rate }: { title: string; rate: Rate }) {
  return (
    <Card>
      <p className="text-sm text-subtle">{title}</p>
      {rate.insufficient_data ? (
        <>
          <p className="mt-1 text-lg font-semibold text-subtle">Insufficient data</p>
          <p className="text-xs text-subtle">
            n = {rate.n}; shown once n ≥ {rate.min_n}
          </p>
        </>
      ) : (
        <>
          <p className="mt-1 text-2xl font-semibold tabular-nums">{formatPercent(rate.rate, 1)}</p>
          <p className="text-xs text-subtle">
            {rate.successes}/{rate.n} · 95% CI {formatPercent(rate.ci_low)}–{formatPercent(rate.ci_high)}
          </p>
        </>
      )}
    </Card>
  );
}

function RateTable({ rows }: { rows: { label: string; rate: Rate }[] }) {
  if (rows.length === 0) return <p className="text-sm text-subtle">No submitted applications yet.</p>;
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-subtle">
          <th scope="col" className="py-1 font-medium">Group</th>
          <th scope="col" className="py-1 text-right font-medium">n</th>
          <th scope="col" className="py-1 text-right font-medium">Rate (95% CI)</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-border">
        {rows.map((r) => (
          <tr key={r.label}>
            <th scope="row" className="py-1.5 text-left font-normal">
              {r.label}
            </th>
            <td className="py-1.5 text-right tabular-nums">{r.rate.n}</td>
            <td className="py-1.5 text-right tabular-nums">
              {r.rate.insufficient_data ? (
                <span className="text-subtle">insufficient data</span>
              ) : (
                `${formatPercent(r.rate.rate)} (${formatPercent(r.rate.ci_low)}–${formatPercent(r.rate.ci_high)})`
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ChartFrame({ label, n, children }: { label: string; n: number; children: React.ReactElement }) {
  if (n === 0) return <p className="py-8 text-center text-sm text-subtle">No data yet (n = 0).</p>;
  return (
    <div className="h-56" role="img" aria-label={`${label}, n = ${n}`}>
      <ResponsiveContainer>{children}</ResponsiveContainer>
    </div>
  );
}
