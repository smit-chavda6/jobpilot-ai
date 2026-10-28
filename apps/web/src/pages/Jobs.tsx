import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Archive, Bookmark, ExternalLink, Plus, RefreshCw, Save, ShieldAlert, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api, errorMessage } from "@/api/client";
import type { FailedImport, JobSummary, Page, SavedFilter } from "@/api/types";
import { ActionBadge, ScorePill } from "@/components/domain";
import { ImportJobsDialog } from "@/components/ImportJobs";
import { useToast } from "@/components/Toast";
import { Badge, Button, Card, Checkbox, DemoBadge, EmptyState, ErrorState, Input, PageHeader, Select, Spinner } from "@/components/ui";
import { formatDate, formatSalary, humanize } from "@/lib/format";

const FILTER_KEYS = ["q", "min_score", "action", "source", "remote", "sort", "include_archived"] as const;
const ROW_HEIGHT = 76;

export default function Jobs() {
  const [params, setParams] = useSearchParams();
  const qc = useQueryClient();
  const toast = useToast();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const filters = useMemo(() => Object.fromEntries(FILTER_KEYS.map((k) => [k, params.get(k) ?? ""])) as Record<(typeof FILTER_KEYS)[number], string>, [params]);
  const setFilter = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next, { replace: true });
    setSelected(new Set());
  };

  const jobs = useInfiniteQuery({
    queryKey: ["jobs", filters],
    queryFn: ({ pageParam }) =>
      api.get<Page<JobSummary>>("/api/jobs", { ...filters, cursor: pageParam as string | undefined, limit: 100 }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    refetchInterval: (query) =>
      query.state.data?.pages.some((p) => p.items.some((j) => !j.match)) && query.state.dataUpdateCount < 20 ? 4000 : false,
  });
  const items = useMemo(() => jobs.data?.pages.flatMap((p) => p.items) ?? [], [jobs.data]);

  const bulk = useMutation({
    mutationFn: (action: "archive" | "unarchive" | "save_to_tracker") => api.post<Record<string, unknown>>("/api/jobs/bulk", { job_ids: [...selected], action }),
    onSuccess: (_r, action) => {
      toast.success(action === "save_to_tracker" ? `Saved ${selected.size} to tracker` : `${humanize(action)}d ${selected.size} job(s)`);
      setSelected(new Set());
      void qc.invalidateQueries({ queryKey: ["jobs"] });
      void qc.invalidateQueries({ queryKey: ["applications"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const rescore = useMutation({
    mutationFn: () => api.post<{ scored: number }>("/api/matches/rescore"),
    onSuccess: (r) => {
      toast.success(`Re-scored ${r.scored} jobs`);
      void qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const allSelected = items.length > 0 && items.every((j) => selected.has(j.id));
  return (
    <>
      <PageHeader
        title="Jobs"
        description="Every job you imported, scored against your confirmed facts and preferences."
        actions={
          <>
            <Button variant="secondary" icon={<RefreshCw className="h-4 w-4" aria-hidden />} loading={rescore.isPending} onClick={() => rescore.mutate()}>
              Re-score
            </Button>
            <Button icon={<Plus className="h-4 w-4" aria-hidden />} onClick={() => setFilter("import", "1")}>
              Import jobs
            </Button>
          </>
        }
      />
      <ImportJobsDialog open={params.get("import") === "1"} onClose={() => setFilter("import", "")} />

      <Card className="mb-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <Input aria-label="Search title, company or location" placeholder="Search…" defaultValue={filters.q} onKeyDown={(e) => e.key === "Enter" && setFilter("q", e.currentTarget.value)} onBlur={(e) => e.target.value !== filters.q && setFilter("q", e.target.value)} className="lg:col-span-2" />
          <Select aria-label="Minimum score" value={filters.min_score} onChange={(e) => setFilter("min_score", e.target.value)}>
            <option value="">Any score</option>
            <option value="50">50+</option>
            <option value="70">70+</option>
            <option value="85">85+</option>
          </Select>
          <Select aria-label="Recommended action" value={filters.action} onChange={(e) => setFilter("action", e.target.value)}>
            <option value="">Any recommendation</option>
            <option value="apply">Apply</option>
            <option value="apply_after_tailoring">Apply after tailoring</option>
            <option value="research_first">Research first</option>
            <option value="skip">Skip</option>
          </Select>
          <Select aria-label="Remote policy" value={filters.remote} onChange={(e) => setFilter("remote", e.target.value)}>
            <option value="">Any work mode</option>
            <option value="remote">Remote</option>
            <option value="hybrid">Hybrid</option>
            <option value="onsite">On-site</option>
          </Select>
          <Select aria-label="Sort" value={filters.sort || "score"} onChange={(e) => setFilter("sort", e.target.value === "score" ? "" : e.target.value)}>
            <option value="score">Best match</option>
            <option value="recent">Most recent</option>
          </Select>
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <Checkbox label="Show archived" checked={filters.include_archived === "true"} onChange={(e) => setFilter("include_archived", e.target.checked ? "true" : "")} />
          <SavedFilters current={filters} onApply={(p) => setParams(new URLSearchParams(p), { replace: true })} />
        </div>
      </Card>

      {selected.size > 0 && (
        <div role="region" aria-label="Bulk actions" className="mb-3 flex flex-wrap items-center gap-2 rounded border border-primary/40 bg-primary/5 p-2 text-sm">
          <span className="px-2 font-medium">{selected.size} selected</span>
          <Button size="sm" variant="secondary" icon={<Bookmark className="h-4 w-4" aria-hidden />} onClick={() => bulk.mutate("save_to_tracker")} loading={bulk.isPending && bulk.variables === "save_to_tracker"}>
            Save to tracker
          </Button>
          <Button size="sm" variant="secondary" icon={<Archive className="h-4 w-4" aria-hidden />} onClick={() => bulk.mutate(filters.include_archived ? "unarchive" : "archive")}>
            {filters.include_archived ? "Unarchive" : "Archive"}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
            Clear
          </Button>
        </div>
      )}

      {jobs.isLoading ? (
        <Spinner label="Loading jobs" />
      ) : jobs.error ? (
        <ErrorState error={jobs.error} onRetry={() => void jobs.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState title={Object.values(filters).some(Boolean) ? "No jobs match these filters" : "No jobs yet"} action={<Button size="sm" onClick={() => setFilter("import", "1")}>Import jobs</Button>}>
          Only sources that permit access are supported. For LinkedIn, Indeed and similar sites, paste the description or forward the alert email.
        </EmptyState>
      ) : (
        <>
          <div className="mb-2 flex items-center gap-3 px-2 text-sm text-subtle">
            <Checkbox
              label={<span className="sr-only">Select all loaded jobs</span>}
              checked={allSelected}
              onChange={(e) => setSelected(e.target.checked ? new Set(items.map((j) => j.id)) : new Set())}
            />
            <span>
              {items.length} job{items.length === 1 ? "" : "s"}
              {jobs.hasNextPage ? "+" : ""}
            </span>
          </div>
          <JobList
            items={items}
            selected={selected}
            onToggle={(id) =>
              setSelected((s) => {
                const n = new Set(s);
                if (n.has(id)) n.delete(id);
                else n.add(id);
                return n;
              })
            }
            onEnd={() => jobs.hasNextPage && !jobs.isFetchingNextPage && void jobs.fetchNextPage()}
          />
          {jobs.isFetchingNextPage && <Spinner label="Loading more" />}
        </>
      )}
      <FailedImports />
    </>
  );
}

/** Virtualised above 100 rows (spec §14); short lists render plainly so they stay fully accessible. */
function JobList({ items, selected, onToggle, onEnd }: { items: JobSummary[]; selected: Set<string>; onToggle: (id: string) => void; onEnd: () => void }) {
  const parent = useRef<HTMLDivElement>(null);
  const virtual = items.length > 100;
  const v = useVirtualizer({ count: items.length, getScrollElement: () => parent.current, estimateSize: () => ROW_HEIGHT, overscan: 8, enabled: virtual });
  if (!virtual) {
    return (
      <ul className="divide-y divide-border rounded-lg border border-border bg-surface" aria-label="Jobs">
        {items.map((j) => (
          <li key={j.id}>
            <JobRow job={j} checked={selected.has(j.id)} onToggle={() => onToggle(j.id)} />
          </li>
        ))}
      </ul>
    );
  }
  return <VirtualRows v={v} parent={parent} items={items} selected={selected} onToggle={onToggle} onEnd={onEnd} />;
}

function VirtualRows({
  v,
  parent,
  items,
  selected,
  onToggle,
  onEnd,
}: {
  v: ReturnType<typeof useVirtualizer<HTMLDivElement, Element>>;
  parent: React.RefObject<HTMLDivElement>;
  items: JobSummary[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  onEnd: () => void;
}) {
  const vItems = v.getVirtualItems();
  const lastIndex = vItems[vItems.length - 1]?.index ?? 0;
  useEffect(() => {
    if (lastIndex >= items.length - 5) onEnd();
  }, [lastIndex, items.length, onEnd]);
  return (
    <div ref={parent} className="h-[70vh] overflow-auto rounded-lg border border-border bg-surface" role="list" aria-label="Jobs">
      <div style={{ height: v.getTotalSize(), position: "relative" }}>
        {vItems.map((row) => {
          const j = items[row.index]!;
          return (
            <div key={j.id} role="listitem" aria-setsize={items.length} aria-posinset={row.index + 1} className="absolute left-0 right-0 border-b border-border" style={{ height: ROW_HEIGHT, transform: `translateY(${row.start}px)` }}>
              <JobRow job={j} checked={selected.has(j.id)} onToggle={() => onToggle(j.id)} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function JobRow({ job, checked, onToggle }: { job: JobSummary; checked: boolean; onToggle: () => void }) {
  const salary = formatSalary(job.salary_min, job.salary_max, job.salary_currency);
  return (
    <div className="flex h-full items-center gap-3 px-3 py-3 hover:bg-muted/40">
      <Checkbox label={<span className="sr-only">Select {job.title} at {job.company}</span>} checked={checked} onChange={onToggle} />
      <div className="min-w-0 flex-1">
        <Link to={`/jobs/${job.id}`} className="block truncate font-medium hover:text-primary">
          {job.title}
        </Link>
        <p className="flex flex-wrap items-center gap-x-2 truncate text-sm text-subtle">
          <span>{job.company}</span>
          {job.location && <span>· {job.location}</span>}
          {job.remote_policy !== "unknown" && <span>· {humanize(job.remote_policy)}</span>}
          {salary && <span>· {salary}</span>}
          <span className="hidden md:inline">· {humanize(job.source)} · {formatDate(job.created_at)}</span>
        </p>
      </div>
      <div className="hidden flex-wrap items-center justify-end gap-2 sm:flex">
        {job.is_demo && <DemoBadge />}
        {job.archived && <Badge>archived</Badge>}
        {job.potential_duplicate_of && <Badge tone="warning">possible duplicate</Badge>}
        {job.scam_level !== "none" && (
          <Badge tone={job.scam_level === "high" ? "danger" : "warning"}>
            <ShieldAlert className="h-3 w-3" aria-hidden /> {job.scam_level} signals
          </Badge>
        )}
        {job.match && <ActionBadge action={job.match.recommended_action} />}
      </div>
      <ScorePill match={job.match} />
      {job.url && (
        <a href={job.url} target="_blank" rel="noopener noreferrer nofollow" className="text-subtle hover:text-fg" aria-label={`Open original posting for ${job.title}`}>
          <ExternalLink className="h-4 w-4" aria-hidden />
        </a>
      )}
    </div>
  );
}

function SavedFilters({ current, onApply }: { current: Record<string, string>; onApply: (p: Record<string, string>) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const saved = useQuery({ queryKey: ["saved-filters"], queryFn: () => api.get<SavedFilter[]>("/api/saved-filters") });
  const put = useMutation({
    mutationFn: (list: SavedFilter[]) => api.put<SavedFilter[]>("/api/saved-filters", list),
    onSuccess: (d) => qc.setQueryData(["saved-filters"], d),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const list = saved.data ?? [];
  const active = Object.fromEntries(Object.entries(current).filter(([, v]) => v));
  return (
    <div className="flex flex-wrap items-center gap-2">
      {list.map((f) => (
        <span key={f.name} className="inline-flex items-center rounded border border-border text-sm">
          <button className="px-2 py-1 hover:bg-muted" onClick={() => onApply(f.params)}>
            {f.name}
          </button>
          <button aria-label={`Delete saved filter ${f.name}`} className="border-l border-border px-1.5 py-1 text-subtle hover:text-danger" onClick={() => put.mutate(list.filter((x) => x.name !== f.name))}>
            <Trash2 className="h-3.5 w-3.5" aria-hidden />
          </button>
        </span>
      ))}
      <Button
        size="sm"
        variant="ghost"
        icon={<Save className="h-4 w-4" aria-hidden />}
        disabled={Object.keys(active).length === 0}
        onClick={() => {
          const name = window.prompt("Name this filter");
          if (name?.trim()) put.mutate([...list.filter((x) => x.name !== name.trim()), { name: name.trim().slice(0, 60), params: active }]);
        }}
      >
        Save filter
      </Button>
    </div>
  );
}

function FailedImports() {
  const qc = useQueryClient();
  const failed = useQuery({ queryKey: ["failed-imports"], queryFn: () => api.get<FailedImport[]>("/api/jobs/failed-imports") });
  const resolve = useMutation({
    mutationFn: (id: string) => api.post(`/api/jobs/failed-imports/${id}/resolve`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["failed-imports"] }),
  });
  if (!failed.data?.length) return null;
  return (
    <Card className="mt-6">
      <details>
        <summary className="cursor-pointer text-sm font-semibold">
          Failed imports ({failed.data.length})
        </summary>
        <ul className="mt-3 divide-y divide-border text-sm">
          {failed.data.map((f) => (
            <li key={f.id} className="flex items-center justify-between gap-2 py-2">
              <span>
                <Badge>{humanize(f.source)}</Badge> <span className="font-medium">{f.input_ref}</span> — {f.error}{" "}
                <span className="text-xs text-subtle">({f.stage}, {formatDate(f.created_at, true)})</span>
              </span>
              <Button size="sm" variant="ghost" onClick={() => resolve.mutate(f.id)}>
                Dismiss
              </Button>
            </li>
          ))}
        </ul>
      </details>
    </Card>
  );
}
