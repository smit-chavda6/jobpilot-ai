import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KanbanSquare, Table2 } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api, errorMessage } from "@/api/client";
import type { ApplicationsPage, ApplicationSummary, AppStatus } from "@/api/types";
import { useToast } from "@/components/Toast";
import { Badge, Button, cn, DemoBadge, EmptyState, PageHeader, QueryView, Select } from "@/components/ui";
import { formatDate, statusLabel } from "@/lib/format";

function useMove() {
  const qc = useQueryClient();
  const toast = useToast();
  const undo = useMutation({
    mutationFn: (id: string) => api.post(`/api/applications/${id}/undo`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["applications"] });
      toast.show("Move undone");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return useMutation({
    mutationFn: ({ app, status }: { app: ApplicationSummary; status: AppStatus }) =>
      api.post<ApplicationSummary>(`/api/applications/${app.id}/move`, { status }, { headers: { "If-Match": `W/"${app.version}"` } }),
    onSuccess: (a, { app }) => {
      void qc.invalidateQueries({ queryKey: ["applications"] });
      void qc.invalidateQueries({ queryKey: ["application", a.id] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success(`Moved “${app.job.title}” to ${statusLabel(a.status)}`, { label: "Undo", onClick: () => undo.mutate(a.id) });
    },
    onError: (e) => {
      void qc.invalidateQueries({ queryKey: ["applications"] });
      toast.error(errorMessage(e));
    },
  });
}

export default function Tracker() {
  const [params, setParams] = useSearchParams();
  const view = params.get("view") === "table" ? "table" : "board";
  const q = useQuery({ queryKey: ["applications"], queryFn: () => api.get<ApplicationsPage>("/api/applications", { limit: 200 }) });
  return (
    <>
      <PageHeader
        title="Tracker"
        description="Every application and its history. Steps that need your approval or confirmation happen in the application workspace."
        actions={
          <div role="group" aria-label="View" className="inline-flex rounded border border-border">
            <Button variant={view === "board" ? "secondary" : "ghost"} size="sm" aria-pressed={view === "board"} icon={<KanbanSquare className="h-4 w-4" aria-hidden />} onClick={() => setParams({}, { replace: true })}>
              Board
            </Button>
            <Button variant={view === "table" ? "secondary" : "ghost"} size="sm" aria-pressed={view === "table"} icon={<Table2 className="h-4 w-4" aria-hidden />} onClick={() => setParams({ view: "table" }, { replace: true })}>
              Table
            </Button>
          </div>
        }
      />
      <QueryView
        query={q}
        isEmpty={(d) => d.items.length === 0}
        empty={
          <EmptyState title="No applications yet" action={<Link to="/jobs"><Button size="sm">Browse jobs</Button></Link>}>
            Open a job and choose “Tailor & prepare application”, or select jobs and “Save to tracker”.
          </EmptyState>
        }
      >
        {(d) => (view === "board" ? <Board data={d} /> : <TableView items={d.items} />)}
      </QueryView>
    </>
  );
}

function Board({ data }: { data: ApplicationsPage }) {
  const move = useMove();
  const [dragging, setDragging] = useState<ApplicationSummary | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const [announce, setAnnounce] = useState("");
  const columns = Object.entries(data.columns);

  const targetIn = (app: ApplicationSummary, statuses: AppStatus[]) => statuses.find((s) => app.allowed_moves.includes(s));

  return (
    <>
      <p className="sr-only" aria-live="assertive">
        {announce}
      </p>
      <p className="mb-3 text-xs text-subtle">Drag a card to another column, or use its “Move to” menu (keyboard and screen-reader friendly). Columns that a card can't move to are dimmed.</p>
      <div className="flex gap-4 overflow-x-auto pb-4">
        {columns.map(([name, statuses]) => {
          const cards = data.items.filter((a) => statuses.includes(a.status));
          const canDrop = dragging ? !!targetIn(dragging, statuses) : true;
          return (
            <section
              key={name}
              aria-label={`${name} column, ${cards.length} applications`}
              className={cn(
                "flex w-72 shrink-0 flex-col rounded-lg border bg-muted/40 p-2",
                over === name && canDrop ? "border-primary" : "border-border",
                dragging && !canDrop && "opacity-50",
              )}
              onDragOver={(e) => {
                if (dragging && canDrop) {
                  e.preventDefault();
                  setOver(name);
                }
              }}
              onDragLeave={() => setOver(null)}
              onDrop={(e) => {
                e.preventDefault();
                setOver(null);
                const target = dragging && targetIn(dragging, statuses);
                if (dragging && target) move.mutate({ app: dragging, status: target });
                setDragging(null);
              }}
            >
              <h2 className="mb-2 flex items-center justify-between px-1 text-sm font-semibold">
                {name} <Badge>{cards.length}</Badge>
              </h2>
              <ul className="flex min-h-[4rem] flex-col gap-2">
                {cards.map((a) => (
                  <li
                    key={a.id}
                    draggable={a.allowed_moves.length > 0}
                    onDragStart={(e) => {
                      e.dataTransfer.effectAllowed = "move";
                      setDragging(a);
                      setAnnounce(`Picked up ${a.job.title}`);
                    }}
                    onDragEnd={() => setDragging(null)}
                    className="cursor-grab rounded border border-border bg-surface p-3 text-sm shadow-sm active:cursor-grabbing"
                  >
                    <Link to={`/applications/${a.id}`} className="font-medium hover:text-primary">
                      {a.job.title}
                    </Link>
                    <p className="text-xs text-subtle">{a.job.company}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-1">
                      <Badge tone="primary">{statusLabel(a.status)}</Badge>
                      {a.is_demo && <DemoBadge />}
                    </div>
                    <p className="mt-1 text-xs text-subtle">Updated {formatDate(a.last_status_at)}</p>
                    <MoveMenu
                      app={a}
                      onMove={(s) => {
                        move.mutate({ app: a, status: s });
                        setAnnounce(`Moving ${a.job.title} to ${statusLabel(s)}`);
                      }}
                    />
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </>
  );
}

function MoveMenu({ app, onMove }: { app: ApplicationSummary; onMove: (s: AppStatus) => void }) {
  if (app.allowed_moves.length === 0) return null;
  return (
    <Select
      aria-label={`Move ${app.job.title} to`}
      className="mt-2 h-8 text-xs"
      value=""
      onChange={(e) => e.target.value && onMove(e.target.value as AppStatus)}
    >
      <option value="">Move to…</option>
      {app.allowed_moves.map((s) => (
        <option key={s} value={s}>
          {statusLabel(s)}
        </option>
      ))}
    </Select>
  );
}

function TableView({ items }: { items: ApplicationSummary[] }) {
  const move = useMove();
  const [sort, setSort] = useState<"last_status_at" | "company" | "status">("last_status_at");
  const sorted = [...items].sort((a, b) =>
    sort === "company" ? a.job.company.localeCompare(b.job.company) : sort === "status" ? a.status.localeCompare(b.status) : b.last_status_at.localeCompare(a.last_status_at),
  );
  const th = (key: typeof sort, label: string) => (
    <th scope="col" aria-sort={sort === key ? (key === "last_status_at" ? "descending" : "ascending") : "none"} className="px-3 py-2 text-left font-medium">
      <button onClick={() => setSort(key)} className="hover:underline">
        {label}
      </button>
    </th>
  );
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-surface">
      <table className="w-full text-sm">
        <thead className="border-b border-border bg-muted/50">
          <tr>
            <th scope="col" className="px-3 py-2 text-left font-medium">Role</th>
            {th("company", "Company")}
            {th("status", "Status")}
            <th scope="col" className="px-3 py-2 text-left font-medium">Submitted</th>
            {th("last_status_at", "Last update")}
            <th scope="col" className="px-3 py-2 text-left font-medium">Move</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {sorted.map((a) => (
            <tr key={a.id}>
              <td className="px-3 py-2">
                <Link to={`/applications/${a.id}`} className="font-medium hover:text-primary">
                  {a.job.title}
                </Link>{" "}
                {a.is_demo && <DemoBadge />}
              </td>
              <td className="px-3 py-2">{a.job.company}</td>
              <td className="px-3 py-2">
                <Badge tone="primary">{statusLabel(a.status)}</Badge>
              </td>
              <td className="px-3 py-2">{formatDate(a.submitted_at)}</td>
              <td className="px-3 py-2">{formatDate(a.last_status_at, true)}</td>
              <td className="px-3 py-2">
                <MoveMenu app={a} onMove={(s) => move.mutate({ app: a, status: s })} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
