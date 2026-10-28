import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, ShieldCheck, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";
import { api, ApiError, errorMessage } from "@/api/client";
import type { Consents, Settings as SettingsData } from "@/api/types";
import { ReauthDialog } from "@/components/domain";
import { useToast } from "@/components/Toast";
import { Badge, Button, Card, CardTitle, Checkbox, Field, Input, Modal, PageHeader, ProgressBar, QueryView } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";

export default function Settings() {
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.get<SettingsData>("/api/settings") });
  return (
    <>
      <PageHeader title="Settings" description="Privacy, notifications, AI budget, and your data." />
      <div className="grid gap-6 lg:grid-cols-2">
        <QueryView query={settings}>
          {(s) => (
            <>
              <AiCard s={s} />
              <PreferencesCard s={s} />
            </>
          )}
        </QueryView>
        <ConsentCard />
        <AccountCard />
        <DataCard />
      </div>
    </>
  );
}

function useSaveSettings() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (patch: Partial<SettingsData>) => api.patch<SettingsData>("/api/settings", patch),
    onSuccess: (d) => {
      qc.setQueryData(["settings"], d);
      toast.success("Settings saved");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
}

function AiCard({ s }: { s: SettingsData }) {
  const save = useSaveSettings();
  const [budget, setBudget] = useState(s.ai_daily_token_budget?.toString() ?? "");
  const pct = s.ai.budget ? (s.ai.used_last_24h / s.ai.budget) * 100 : 0;
  return (
    <Card>
      <CardTitle>AI usage & budget</CardTitle>
      <p className="text-sm">
        Provider: <Badge tone="primary">{s.ai.provider}</Badge>
      </p>
      <div className="mt-3">
        <div className="mb-1 flex justify-between text-xs text-subtle">
          <span>Tokens used in the last 24 h</span>
          <span className="tabular-nums">
            {s.ai.used_last_24h.toLocaleString()} / {s.ai.budget.toLocaleString()}
          </span>
        </div>
        <ProgressBar value={pct} label="AI budget used" tone={pct > 90 ? "danger" : pct > 70 ? "warning" : "primary"} />
      </div>
      <p className="mt-2 text-xs text-subtle">When the budget runs out, features fall back to deterministic rules. Nothing stops working.</p>
      <form
        className="mt-3 flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate({ ai_daily_token_budget: budget === "" ? null : Number(budget) });
        }}
      >
        <Field label="Personal daily token cap" hint="Blank = server default" className="flex-1">
          {(id, d) => <Input id={id} aria-describedby={d} type="number" min={0} value={budget} onChange={(e) => setBudget(e.target.value)} />}
        </Field>
        <Button type="submit" variant="secondary" loading={save.isPending}>
          Save
        </Button>
      </form>
    </Card>
  );
}

function PreferencesCard({ s }: { s: SettingsData }) {
  const save = useSaveSettings();
  const [retention, setRetention] = useState(s.retention_days?.toString() ?? "");
  return (
    <Card>
      <CardTitle>Notifications & retention</CardTitle>
      <div className="space-y-2">
        <Checkbox label="In-app reminders for follow-ups" checked={s.notify_reminders} onChange={(e) => save.mutate({ notify_reminders: e.target.checked })} />
        <Checkbox label="Notify me when uploaded emails need review" checked={s.notify_triage} onChange={(e) => save.mutate({ notify_triage: e.target.checked })} />
      </div>
      <form
        className="mt-4 flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate({ retention_days: retention === "" ? null : Number(retention) });
        }}
      >
        <Field label="Keep AI usage logs and processed event records for (days)" hint="Older records are purged by the worker. Blank = keep until you delete your account." className="flex-1">
          {(id, d) => <Input id={id} aria-describedby={d} type="number" min={1} value={retention} onChange={(e) => setRetention(e.target.value)} />}
        </Field>
        <Button type="submit" variant="secondary" loading={save.isPending}>
          Save
        </Button>
      </form>
    </Card>
  );
}

function ConsentCard() {
  const qc = useQueryClient();
  const toast = useToast();
  const consents = useQuery({ queryKey: ["consents"], queryFn: () => api.get<Consents>("/api/consents") });
  const set = useMutation({
    mutationFn: (granted: boolean) => api.post("/api/consents", { purpose: "ai_processing", granted }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["consents"] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card>
      <CardTitle>
        <span className="inline-flex items-center gap-2">
          <ShieldCheck className="h-4 w-4" aria-hidden /> Consent & data sharing
        </span>
      </CardTitle>
      <QueryView query={consents}>
        {(c) => {
          const ai = c.consents.ai_processing;
          return (
            <div className="space-y-3 text-sm">
              <p>
                AI provider: <strong>{c.ai_provider}</strong>
                {c.ai_provider === "mock" && " — deterministic and local. No data leaves this server."}
              </p>
              {c.ai_provider !== "mock" && (
                <p>
                  Data sent to {c.ai_provider} when you use AI features:{" "}
                  {c.data_sent_to_provider.length ? c.data_sent_to_provider.join("; ") : "nothing"}.
                </p>
              )}
              <Checkbox label="Allow AI processing of my resume, facts and job descriptions" checked={!!ai?.granted} onChange={(e) => set.mutate(e.target.checked)} />
              {ai && <p className="text-xs text-subtle">Last changed {formatDate(ai.at, true)}</p>}
            </div>
          );
        }}
      </QueryView>
    </Card>
  );
}

function AccountCard() {
  const { user } = useAuth();
  const toast = useToast();
  const resend = useMutation({
    mutationFn: () => api.post("/api/auth/request-verification"),
    onSuccess: () => toast.success("Verification email sent (in development, see the API dev mailbox)"),
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card>
      <CardTitle>Account</CardTitle>
      <p className="text-sm">
        {user?.email} {user?.email_verified ? <Badge tone="success">verified</Badge> : <Badge tone="warning">not verified</Badge>}
      </p>
      {!user?.email_verified && (
        <Button size="sm" variant="secondary" className="mt-3" loading={resend.isPending} onClick={() => resend.mutate()}>
          Resend verification email
        </Button>
      )}
    </Card>
  );
}

function DataCard() {
  const toast = useToast();
  const navigate = useNavigate();
  const { setUser, resetData } = useAuth();
  const [reauthFor, setReauthFor] = useState<"export" | "delete" | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [report, setReport] = useState<Record<string, unknown> | null>(null);

  const exportData = useMutation({
    mutationFn: () => api.download("/api/privacy/export", "jobpilot-export.zip", "POST"),
    onSuccess: () => toast.success("Export downloaded"),
    onError: (e) => (e instanceof ApiError && e.code === "reauth_required" ? setReauthFor("export") : toast.error(errorMessage(e))),
  });
  const deleteAccount = useMutation({
    mutationFn: () => api.post<Record<string, unknown>>("/api/privacy/delete-account", { confirm: "DELETE" }),
    onSuccess: (r) => {
      setConfirmOpen(false);
      setReport(r);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === "reauth_required") {
        setConfirmOpen(false);
        setReauthFor("delete");
      } else toast.error(errorMessage(e));
    },
  });
  return (
    <Card>
      <CardTitle>Your data</CardTitle>
      <p className="mb-3 text-sm text-subtle">Export everything (JSON plus uploaded files) or permanently delete your account, files, embeddings and logs linked to you.</p>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" icon={<Download className="h-4 w-4" aria-hidden />} loading={exportData.isPending} onClick={() => exportData.mutate()}>
          Export my data
        </Button>
        <Button variant="danger" icon={<Trash2 className="h-4 w-4" aria-hidden />} onClick={() => setConfirmOpen(true)}>
          Delete account
        </Button>
      </div>
      <Modal
        open={confirmOpen}
        title="Delete your account permanently?"
        onClose={() => setConfirmOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button variant="danger" disabled={typed !== "DELETE"} loading={deleteAccount.isPending} onClick={() => deleteAccount.mutate()}>
              Delete everything
            </Button>
          </>
        }
      >
        <p>This removes your profile, facts, resumes, jobs, applications, documents, emails and logs linked to you. It can't be undone.</p>
        <Field label='Type "DELETE" to confirm'>{(id) => <Input id={id} value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />}</Field>
      </Modal>
      <ReauthDialog
        open={reauthFor !== null}
        reason={reauthFor === "export" ? "Exporting your data requires your password." : "Deleting your account requires your password."}
        onClose={() => setReauthFor(null)}
        onDone={() => {
          const what = reauthFor;
          setReauthFor(null);
          if (what === "export") exportData.mutate();
          else setConfirmOpen(true);
        }}
      />
      <Modal
        open={report !== null}
        title="Account deleted"
        onClose={() => {
          resetData();
          setUser(null);
          navigate("/register", { replace: true });
        }}
        footer={
          <Button
            onClick={() => {
              resetData();
              setUser(null);
              navigate("/register", { replace: true });
            }}
          >
            Done
          </Button>
        }
      >
        <p>Verified deletion report:</p>
        <pre className="max-h-60 overflow-auto rounded bg-muted p-2 text-xs">{JSON.stringify(report, null, 2)}</pre>
      </Modal>
    </Card>
  );
}
