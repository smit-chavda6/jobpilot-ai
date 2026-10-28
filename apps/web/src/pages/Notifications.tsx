import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCheck } from "lucide-react";
import { Link } from "react-router";
import { api } from "@/api/client";
import type { Notification } from "@/api/types";
import { Badge, Button, Card, cn, EmptyState, PageHeader, QueryView } from "@/components/ui";
import { formatDate, humanize } from "@/lib/format";

export default function Notifications() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["notifications"], queryFn: () => api.get<Notification[]>("/api/notifications") });
  const readAll = useMutation({
    mutationFn: () => api.post("/api/notifications/read-all"),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["notifications"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
  return (
    <>
      <PageHeader
        title="Notifications"
        description="In-app only. JobPilot never sends email on your behalf."
        actions={
          <Button variant="secondary" icon={<CheckCheck className="h-4 w-4" aria-hidden />} loading={readAll.isPending} onClick={() => readAll.mutate()}>
            Mark all read
          </Button>
        }
      />
      <QueryView query={q} isEmpty={(d) => d.length === 0} empty={<EmptyState title="You're all caught up" />}>
        {(list) => (
          <Card className="p-0">
            <ul className="divide-y divide-border">
              {list.map((n) => (
                <li key={n.id} className={cn("flex items-start gap-3 px-4 py-3 text-sm", !n.read && "bg-primary/5")}>
                  {!n.read && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary" aria-label="unread" />}
                  <div className="flex-1">
                    {n.link ? (
                      <Link to={n.link} className="hover:text-primary">
                        {n.message}
                      </Link>
                    ) : (
                      n.message
                    )}
                    <p className="text-xs text-subtle">{formatDate(n.created_at, true)}</p>
                  </div>
                  <Badge>{humanize(n.kind)}</Badge>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </QueryView>
    </>
  );
}
