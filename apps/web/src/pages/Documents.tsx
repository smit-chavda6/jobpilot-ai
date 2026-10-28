import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, errorMessage, newIdempotencyKey } from "@/api/client";
import type { DocumentSummary } from "@/api/types";
import { useToast } from "@/components/Toast";
import { Badge, Button, Card, EmptyState, PageHeader, QueryView } from "@/components/ui";
import { formatDate, humanize } from "@/lib/format";

export default function Documents() {
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const docs = useQuery({ queryKey: ["documents"], queryFn: () => api.get<DocumentSummary[]>("/api/documents") });
  const [key] = useState(newIdempotencyKey);
  const generate = useMutation({
    mutationFn: (kind: "resume" | "cover_letter") => api.post<DocumentSummary>("/api/documents", { kind }, { idempotencyKey: `${key}-${kind}-${Date.now()}` }),
    onSuccess: (d) => {
      void qc.invalidateQueries({ queryKey: ["documents"] });
      navigate(`/documents/${d.id}`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const del = useMutation({
    mutationFn: (id: string) => api.del(`/api/documents/${id}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["documents"] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <>
      <PageHeader
        title="Resume Studio"
        description="Generated resumes and cover letters. Every claim cites your confirmed facts; ungrounded items block export."
        actions={
          <Button icon={<Plus className="h-4 w-4" aria-hidden />} loading={generate.isPending} onClick={() => generate.mutate("resume")}>
            New general resume
          </Button>
        }
      />
      <QueryView
        query={docs}
        isEmpty={(d) => d.length === 0}
        empty={
          <EmptyState title="No documents yet">
            Open a job and choose “Tailor & prepare application”, or generate a general resume from your confirmed facts.
          </EmptyState>
        }
      >
        {(list) => (
          <Card className="p-0">
            <ul className="divide-y divide-border">
              {list.map((d) => (
                <li key={d.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                  <FileText className="h-5 w-5 text-subtle" aria-hidden />
                  <div className="min-w-0 flex-1">
                    <Link to={`/documents/${d.id}`} className="font-medium hover:text-primary">
                      {d.title}
                    </Link>
                    <p className="text-xs text-subtle">
                      {humanize(d.kind)} · v{d.version} · updated {formatDate(d.updated_at, true)} · {d.generator}
                    </p>
                  </div>
                  <Badge tone={d.grounded ? "success" : "danger"}>{d.grounded ? "Grounded" : `${d.grounding_report.failed} ungrounded`}</Badge>
                  <Button size="sm" variant="ghost" aria-label={`Delete ${d.title}`} onClick={() => window.confirm(`Delete “${d.title}”?`) && del.mutate(d.id)}>
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </Button>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </QueryView>
    </>
  );
}
