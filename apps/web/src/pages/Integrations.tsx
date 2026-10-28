import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, ExternalLink, Mail } from "lucide-react";
import { useState } from "react";
import { api, ApiError, errorMessage } from "@/api/client";
import type { DisabledSource, Integrations as IntegrationsData, Source } from "@/api/types";
import { ReauthDialog } from "@/components/domain";
import { useToast } from "@/components/Toast";
import { Badge, Button, Card, CardTitle, PageHeader, QueryView } from "@/components/ui";
import { humanize } from "@/lib/format";

export default function Integrations() {
  const sources = useQuery({ queryKey: ["sources"], queryFn: () => api.get<{ sources: Source[]; disabled_by_policy: DisabledSource[] }>("/api/sources") });
  const integrations = useQuery({ queryKey: ["integrations"], queryFn: () => api.get<IntegrationsData>("/api/integrations") });
  return (
    <>
      <PageHeader
        title="Sources & Integrations"
        description="JobPilot only uses access methods a source's terms permit. Each source can be switched off for your account. See docs/sources.md for the compliance registry."
      />
      <div className="space-y-6">
        <Card>
          <CardTitle>Job sources</CardTitle>
          <QueryView query={sources}>{(d) => <SourceTable sources={d.sources} />}</QueryView>
        </Card>
        <Card>
          <CardTitle>
            <span className="inline-flex items-center gap-2">
              <Ban className="h-4 w-4" aria-hidden /> Not automated, by policy
            </span>
          </CardTitle>
          <p className="mb-3 text-sm text-subtle">These sites' terms prohibit scraping or automated access, so JobPilot never fetches from them. Use the manual path instead.</p>
          <QueryView query={sources}>
            {(d) => (
              <ul className="grid gap-3 md:grid-cols-2">
                {d.disabled_by_policy.map((s) => (
                  <li key={s.id} className="rounded border border-border p-3 text-sm">
                    <p className="font-medium">{s.name}</p>
                    <p className="mt-1 text-subtle">{s.reason}</p>
                    <p className="mt-2">
                      <strong>Instead:</strong> {s.manual_path}
                    </p>
                    <a href={s.tos_url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline">
                      Terms (reviewed {s.reviewed_on}) <ExternalLink className="h-3 w-3" aria-hidden />
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </QueryView>
        </Card>
        <Card>
          <CardTitle>
            <span className="inline-flex items-center gap-2">
              <Mail className="h-4 w-4" aria-hidden /> Email accounts
            </span>
          </CardTitle>
          <QueryView query={integrations}>{(d) => <EmailIntegrations data={d} />}</QueryView>
        </Card>
      </div>
    </>
  );
}

function SourceTable({ sources }: { sources: Source[] }) {
  const qc = useQueryClient();
  const toast = useToast();
  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => api.put(`/api/sources/${id}`, { enabled }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["sources"] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-subtle">
            <th scope="col" className="py-2 pr-3 font-medium">Source</th>
            <th scope="col" className="py-2 pr-3 font-medium">Permitted method</th>
            <th scope="col" className="py-2 pr-3 font-medium">Capabilities</th>
            <th scope="col" className="py-2 pr-3 font-medium">Reviewed</th>
            <th scope="col" className="py-2 font-medium">Enabled</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {sources.map((s) => (
            <tr key={s.id} className="align-top">
              <td className="py-2 pr-3">
                <p className="font-medium">{s.name}</p>
                <p className="text-xs text-subtle">{s.compliance.notes}</p>
              </td>
              <td className="py-2 pr-3">{s.compliance.allowed_methods.map(humanize).join(", ")}</td>
              <td className="py-2 pr-3">
                <div className="flex flex-wrap gap-1">
                  {Object.entries(s.capabilities)
                    .filter(([, v]) => v)
                    .map(([k]) => (
                      <Badge key={k}>{humanize(k)}</Badge>
                    ))}
                </div>
              </td>
              <td className="py-2 pr-3 whitespace-nowrap">
                {s.compliance.tos_url.startsWith("http") ? (
                  <a className="text-primary hover:underline" href={s.compliance.tos_url} target="_blank" rel="noopener noreferrer">
                    {s.compliance.reviewed_on}
                  </a>
                ) : (
                  s.compliance.reviewed_on
                )}
              </td>
              <td className="py-2">
                <label className="inline-flex items-center gap-2">
                  <input
                    type="checkbox"
                    role="switch"
                    aria-checked={s.enabled}
                    aria-label={`Enable ${s.name}`}
                    className="h-4 w-4 accent-[rgb(var(--primary))]"
                    checked={s.enabled}
                    onChange={(e) => toggle.mutate({ id: s.id, enabled: e.target.checked })}
                  />
                  <span className="sr-only">{s.enabled ? "On" : "Off"}</span>
                </label>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EmailIntegrations({ data }: { data: IntegrationsData }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [pending, setPending] = useState<string | null>(null);
  const disconnect = useMutation({
    mutationFn: (id: string) => api.del(`/api/integrations/${id}`),
    onSuccess: () => {
      setPending(null);
      void qc.invalidateQueries({ queryKey: ["integrations"] });
      toast.success("Disconnected and tokens deleted");
    },
    onError: (e, id) => {
      if (e instanceof ApiError && e.code === "reauth_required") setPending(id);
      else toast.error(errorMessage(e));
    },
  });
  return (
    <>
      {data.connected.length > 0 && (
        <ul className="mb-4 space-y-2 text-sm">
          {data.connected.map((c) => (
            <li key={c.id} className="flex items-center justify-between rounded border border-border p-3">
              <span>
                {humanize(c.provider)} <Badge>{c.status}</Badge>
              </span>
              <Button size="sm" variant="danger" onClick={() => disconnect.mutate(c.id)}>
                Disconnect
              </Button>
            </li>
          ))}
        </ul>
      )}
      <ul className="grid gap-3 md:grid-cols-2">
        {data.available.map((a) => (
          <li key={a.provider} className="rounded border border-border p-3 text-sm">
            <p className="flex items-center justify-between font-medium">
              {humanize(a.provider)} <Badge tone="warning">Not available in this build</Badge>
            </p>
            <p className="mt-1 text-subtle">{a.note}</p>
            <p className="mt-2 text-xs text-subtle">Would request read-only scopes: {a.scopes.join(", ")}</p>
          </li>
        ))}
      </ul>
      <ReauthDialog
        open={pending !== null}
        reason="Disconnecting an integration requires your password."
        onClose={() => setPending(null)}
        onDone={() => pending && disconnect.mutate(pending)}
      />
    </>
  );
}
