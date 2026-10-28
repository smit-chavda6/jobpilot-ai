import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { api, errorMessage } from "@/api/client";
import type { Fact, Profile as ProfileData, ResumeFile, ResumeUpload } from "@/api/types";
import { FactEditor, FactReview } from "@/components/domain";
import { BasicsForm, PreferencesForm } from "@/components/ProfileForms";
import { useToast } from "@/components/Toast";
import { Badge, Button, Card, CardTitle, EmptyState, PageHeader, QueryView, Select } from "@/components/ui";
import { formatDate } from "@/lib/format";

export default function Profile() {
  const profile = useQuery({ queryKey: ["profile"], queryFn: () => api.get<ProfileData>("/api/profile") });
  const [status, setStatus] = useState("");
  const facts = useQuery({ queryKey: ["facts", status], queryFn: () => api.get<Fact[]>("/api/facts", { status }) });
  const [adding, setAdding] = useState(false);
  return (
    <>
      <PageHeader
        title="Profile & Facts"
        description="Your verified profile is the single source of truth. Matching and every generated document use only confirmed facts."
      />
      <div className="grid gap-6 xl:grid-cols-5">
        <div className="space-y-6 xl:col-span-3">
          <Card>
            <CardTitle
              action={
                <div className="flex gap-2">
                  <Select aria-label="Filter facts by status" value={status} onChange={(e) => setStatus(e.target.value)} className="h-8 w-40 text-xs">
                    <option value="">All facts</option>
                    <option value="candidate">Unconfirmed</option>
                    <option value="confirmed">Confirmed</option>
                    <option value="rejected">Rejected</option>
                  </Select>
                  <Button size="sm" icon={<Plus className="h-4 w-4" aria-hidden />} onClick={() => setAdding(true)}>
                    Add fact
                  </Button>
                </div>
              }
            >
              Facts
            </CardTitle>
            <QueryView query={facts} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No facts">Upload a resume or add facts by hand.</EmptyState>}>
              {(d) => <FactReview facts={d} />}
            </QueryView>
          </Card>
        </div>
        <div className="space-y-6 xl:col-span-2">
          <Resumes />
          <Skills />
          <QueryView query={profile}>
            {(p) => (
              <>
                <Card>
                  <CardTitle>About you</CardTitle>
                  <BasicsForm key={`b${p.version}`} profile={p} />
                </Card>
                <Card>
                  <CardTitle>Job preferences & hard filters</CardTitle>
                  <PreferencesForm key={`p${p.version}`} profile={p} />
                </Card>
              </>
            )}
          </QueryView>
        </div>
      </div>
      <FactEditor fact={adding ? "new" : null} onClose={() => setAdding(false)} />
    </>
  );
}

function Resumes() {
  const qc = useQueryClient();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const resumes = useQuery({ queryKey: ["resumes"], queryFn: () => api.get<ResumeFile[]>("/api/resumes") });
  const upload = useMutation({
    mutationFn: (f: File) => api.upload<ResumeUpload>("/api/resumes", f),
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: ["resumes"] });
      void qc.invalidateQueries({ queryKey: ["facts"] });
      if (r.parse_status === "parsed") toast.success(`Found ${r.facts.length} candidate facts to review`);
      else toast.error(r.parse_error ?? "Couldn't parse this file");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const del = useMutation({
    mutationFn: (id: string) => api.del(`/api/resumes/${id}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["resumes"] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card>
      <CardTitle
        action={
          <>
            <input
              ref={input}
              type="file"
              className="sr-only"
              aria-label="Resume file"
              accept=".pdf,.docx,.txt"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) upload.mutate(f);
                e.target.value = "";
              }}
            />
            <Button size="sm" variant="secondary" icon={<Upload className="h-4 w-4" aria-hidden />} loading={upload.isPending} onClick={() => input.current?.click()}>
              Upload
            </Button>
          </>
        }
      >
        Resumes
      </CardTitle>
      <QueryView query={resumes} isEmpty={(d) => d.length === 0} empty={<p className="text-sm text-subtle">No resumes uploaded.</p>}>
        {(list) => (
          <ul className="divide-y divide-border text-sm">
            {list.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-2 py-2">
                <span className="min-w-0">
                  <span className="block truncate font-medium">{r.filename}</span>
                  <span className="text-xs text-subtle">
                    {(r.size_bytes / 1024).toFixed(0)} KB · {formatDate(r.created_at)}
                  </span>
                </span>
                <Badge tone={r.parse_status === "parsed" ? "success" : "danger"}>{r.parse_status}</Badge>
                <Button size="sm" variant="ghost" aria-label={`Delete ${r.filename}`} onClick={() => window.confirm(`Delete ${r.filename}? Facts already confirmed are kept.`) && del.mutate(r.id)}>
                  <Trash2 className="h-4 w-4" aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </QueryView>
    </Card>
  );
}

function Skills() {
  const skills = useQuery({ queryKey: ["skills"], queryFn: () => api.get<string[]>("/api/skills") });
  return (
    <Card>
      <CardTitle>Verified skills</CardTitle>
      <p className="mb-2 text-xs text-subtle">Derived from confirmed facts only.</p>
      <QueryView query={skills} isEmpty={(d) => d.length === 0} empty={<p className="text-sm text-subtle">Confirm facts to see skills here.</p>}>
        {(list) => (
          <div className="flex flex-wrap gap-1">
            {list.map((s) => (
              <Badge key={s} tone="success">
                {s}
              </Badge>
            ))}
          </div>
        )}
      </QueryView>
    </Card>
  );
}
