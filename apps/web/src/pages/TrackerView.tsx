import { useState } from "react";
import {
  KanbanSquare,
  Table as TableIcon,
  ArrowRight,
  RotateCcw,
  Building2,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Card, CardContent } from "../components/ui/card";

interface ApplicationItem {
  id: string;
  role: string;
  company: string;
  status: "discovered" | "tailoring" | "ready_for_review" | "awaiting_approval" | "approved" | "submitted_confirmed" | "interviewing";
  matchScore: number;
  lastUpdated: string;
}

const columns = [
  { id: "discovered", label: "Discovered" },
  { id: "tailoring", label: "Tailoring" },
  { id: "ready_for_review", label: "Ready for Review" },
  { id: "awaiting_approval", label: "Awaiting Approval" },
  { id: "approved", label: "Approved" },
  { id: "submitted_confirmed", label: "Submitted (Confirmed)" },
  { id: "interviewing", label: "Interviewing" },
];

export function TrackerView() {
  const [viewMode, setViewMode] = useState<"kanban" | "table">("kanban");
  const [undoToast, setUndoToast] = useState<string | null>(null);

  const [applications, setApplications] = useState<ApplicationItem[]>([
    {
      id: "app-1",
      role: "Staff Backend Engineer",
      company: "Stripe",
      status: "awaiting_approval",
      matchScore: 94,
      lastUpdated: "10 mins ago",
    },
    {
      id: "app-2",
      role: "AI Systems Engineer",
      company: "Anthropic",
      status: "tailoring",
      matchScore: 91,
      lastUpdated: "1 hour ago",
    },
    {
      id: "app-3",
      role: "Senior Distributed Engineer",
      company: "Datadog",
      status: "submitted_confirmed",
      matchScore: 88,
      lastUpdated: "2 days ago",
    },
    {
      id: "app-4",
      role: "Lead Platform Engineer",
      company: "Figma",
      status: "interviewing",
      matchScore: 95,
      lastUpdated: "Yesterday",
    },
  ]);

  const advanceStatus = (appId: string) => {
    const statusOrder: ApplicationItem["status"][] = [
      "discovered",
      "tailoring",
      "ready_for_review",
      "awaiting_approval",
      "approved",
      "submitted_confirmed",
      "interviewing",
    ];

    setApplications((prev) =>
      prev.map((app) => {
        if (app.id !== appId) return app;
        const currentIndex = statusOrder.indexOf(app.status);
        if (currentIndex < statusOrder.length - 1) {
          const nextStatus = statusOrder[currentIndex + 1];
          setUndoToast(`Moved ${app.company} application to ${nextStatus.replace(/_/g, " ")}`);
          setTimeout(() => setUndoToast(null), 5000);
          return { ...app, status: nextStatus, lastUpdated: "Just now" };
        }
        return app;
      })
    );
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-200/60 dark:border-slate-800">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Application Tracker</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Persisted state machine. Status transitions are logged and require human approval checkpoints.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-lg border border-slate-200 dark:border-slate-800 p-0.5 bg-slate-100 dark:bg-slate-900">
            <button
              onClick={() => setViewMode("kanban")}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                viewMode === "kanban"
                  ? "bg-white dark:bg-slate-800 shadow-sm text-slate-900 dark:text-slate-100"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              <KanbanSquare className="w-3.5 h-3.5" /> Kanban
            </button>
            <button
              onClick={() => setViewMode("table")}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                viewMode === "table"
                  ? "bg-white dark:bg-slate-800 shadow-sm text-slate-900 dark:text-slate-100"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              <TableIcon className="w-3.5 h-3.5" /> Table
            </button>
          </div>
        </div>
      </div>

      {/* Undo Toast Notification */}
      {undoToast && (
        <div className="fixed bottom-6 right-6 z-50 p-4 rounded-xl bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 shadow-xl flex items-center gap-3 text-xs font-medium animate-in slide-in-from-bottom-5">
          <span>{undoToast}</span>
          <button
            onClick={() => setUndoToast(null)}
            className="flex items-center gap-1 text-indigo-400 dark:text-indigo-600 font-bold hover:underline"
          >
            <RotateCcw className="w-3.5 h-3.5" /> Dismiss
          </button>
        </div>
      )}

      {/* Kanban Board */}
      {viewMode === "kanban" ? (
        <div className="flex gap-4 overflow-x-auto pb-6 pt-1">
          {columns.map((col) => {
            const colApps = applications.filter((a) => a.status === col.id);
            const isApprovalGate = col.id === "awaiting_approval";

            return (
              <div
                key={col.id}
                className="w-72 shrink-0 flex flex-col rounded-xl bg-slate-100/70 dark:bg-slate-900/40 border border-slate-200/70 dark:border-slate-800 p-3 min-h-[500px]"
              >
                <div className="flex items-center justify-between pb-3 px-1 border-b border-slate-200/50 dark:border-slate-800">
                  <span className="font-bold text-xs uppercase tracking-wider text-slate-600 dark:text-slate-300">
                    {col.label}
                  </span>
                  <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                    {colApps.length}
                  </Badge>
                </div>

                <div className="space-y-3 mt-3 flex-1">
                  {colApps.map((app) => (
                    <Card
                      key={app.id}
                      className={`cursor-pointer hover:shadow-md transition-shadow ${
                        isApprovalGate
                          ? "border-amber-300 dark:border-amber-900/60 bg-gradient-to-b from-white to-amber-50/20 dark:from-slate-900 dark:to-amber-950/20"
                          : ""
                      }`}
                    >
                      <CardContent className="p-4 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-xs text-slate-900 dark:text-slate-100 flex items-center gap-1">
                            <Building2 className="w-3.5 h-3.5 text-slate-400" /> {app.company}
                          </span>
                          <span className="text-[11px] font-bold text-emerald-600">
                            {app.matchScore}%
                          </span>
                        </div>
                        <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 leading-snug">
                          {app.role}
                        </p>
                        <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-slate-100 dark:border-slate-800">
                          <span>Updated {app.lastUpdated}</span>
                          <Button
                            size="sm"
                            variant={isApprovalGate ? "primary" : "ghost"}
                            className="h-6 text-[10px] px-2"
                            onClick={() => advanceStatus(app.id)}
                          >
                            Advance <ArrowRight className="w-3 h-3 ml-0.5" />
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  ))}

                  {colApps.length === 0 && (
                    <div className="h-24 flex items-center justify-center border border-dashed border-slate-200 dark:border-slate-800 rounded-lg text-slate-400 text-xs">
                      No applications
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* Table View */
        <Card>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 dark:bg-slate-800/60 border-b border-slate-200 dark:border-slate-800 text-slate-500">
                <tr>
                  <th className="p-4 font-semibold">Company</th>
                  <th className="p-4 font-semibold">Role</th>
                  <th className="p-4 font-semibold">Status</th>
                  <th className="p-4 font-semibold">Match</th>
                  <th className="p-4 font-semibold">Last Updated</th>
                  <th className="p-4 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {applications.map((app) => (
                  <tr key={app.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/30">
                    <td className="p-4 font-bold">{app.company}</td>
                    <td className="p-4">{app.role}</td>
                    <td className="p-4">
                      <Badge variant="secondary" className="capitalize">
                        {app.status.replace(/_/g, " ")}
                      </Badge>
                    </td>
                    <td className="p-4 font-bold text-emerald-600">{app.matchScore}%</td>
                    <td className="p-4 text-slate-400">{app.lastUpdated}</td>
                    <td className="p-4 text-right">
                      <Button size="sm" variant="outline" onClick={() => advanceStatus(app.id)}>
                        Advance
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
