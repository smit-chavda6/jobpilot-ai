import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router";
import { api, errorMessage, newIdempotencyKey } from "@/api/client";
import type { ImportResult, Source } from "@/api/types";
import { useToast } from "./Toast";
import { Badge, Button, cn, Field, Input, Modal, Textarea } from "./ui";

type Tab = "manual_paste" | "manual_url" | "file" | "email" | "greenhouse" | "lever" | "ashby" | "rss";

const TABS: { id: Tab; label: string; param?: "text" | "url" | "board" | "company" | "organization"; hint?: string }[] = [
  { id: "manual_paste", label: "Paste", param: "text" },
  { id: "manual_url", label: "URL", param: "url", hint: "One public job page. Private, internal and metadata addresses are blocked; robots.txt is honoured." },
  { id: "file", label: "CSV / JSON" },
  { id: "email", label: "Alert email" },
  { id: "greenhouse", label: "Greenhouse", param: "board", hint: "Board token from boards.greenhouse.io/<token> (public Job Board API)." },
  { id: "lever", label: "Lever", param: "company", hint: "Company slug from jobs.lever.co/<company> (public Postings API)." },
  { id: "ashby", label: "Ashby", param: "organization", hint: "Organisation from jobs.ashbyhq.com/<organization> (public Job Board API)." },
  { id: "rss", label: "RSS feed", param: "url", hint: "An official RSS/Atom job feed URL." },
];

export function ImportJobsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("manual_paste");
  const [value, setValue] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);
  // One key per dialog submission so double-clicks and retries never import twice.
  const [idemKey, setIdemKey] = useState(newIdempotencyKey);
  const fileRef = useRef<HTMLInputElement>(null);
  const sources = useQuery({ queryKey: ["sources"], queryFn: () => api.get<{ sources: Source[] }>("/api/sources"), enabled: open });
  const enabled = (id: string) => sources.data?.sources.find((s) => s.id === id)?.enabled ?? true;

  const done = (r: ImportResult) => {
    setResult(r);
    setIdemKey(newIdempotencyKey());
    void qc.invalidateQueries({ queryKey: ["jobs"] });
    void qc.invalidateQueries({ queryKey: ["dashboard"] });
    void qc.invalidateQueries({ queryKey: ["failed-imports"] });
    toast.success(`Imported ${r.counts.created} new, ${r.counts.updated} updated${r.counts.failed ? `, ${r.counts.failed} failed` : ""}`);
  };
  const importParam = useMutation({
    mutationFn: () => {
      const def = TABS.find((t) => t.id === tab)!;
      return api.post<ImportResult>(`/api/jobs/import/${tab}`, { [def.param!]: value.trim() }, { idempotencyKey: idemKey });
    },
    onSuccess: done,
    onError: (e) => toast.error(errorMessage(e)),
  });
  const importFile = useMutation({
    mutationFn: (f: File) => api.upload<ImportResult>(tab === "email" ? "/api/jobs/import/email" : "/api/jobs/import/file", f, { idempotencyKey: idemKey }),
    onSuccess: done,
    onError: (e) => toast.error(errorMessage(e)),
  });

  const def = TABS.find((t) => t.id === tab)!;
  const close = () => {
    setResult(null);
    setValue("");
    onClose();
  };
  return (
    <Modal open={open} title="Import jobs" onClose={close} footer={<Button variant="secondary" onClick={close}>Close</Button>}>
      <div role="tablist" aria-label="Import source" className="flex flex-wrap gap-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={cn("rounded px-2.5 py-1 text-xs font-medium", tab === t.id ? "bg-primary text-primary-fg" : "bg-muted text-subtle hover:text-fg")}
            onClick={() => {
              setTab(t.id);
              setValue("");
              setResult(null);
            }}
          >
            {t.label}
          </button>
        ))}
      </div>
      {!enabled(tab === "file" ? "file_import" : tab === "email" ? "email_upload" : tab) ? (
        <p className="rounded border border-warning/40 bg-warning/5 p-3">
          This source is disabled. Enable it in <Link className="text-primary underline" to="/integrations">Sources & Integrations</Link>.
        </p>
      ) : tab === "file" || tab === "email" ? (
        <div className="space-y-2">
          <p className="text-subtle">
            {tab === "file"
              ? "CSV with columns title, company, location, url, description (or a JSON array of objects with those keys)."
              : "A job-alert email saved as .eml or a mailbox export (.mbox). Jobs linked in the email are imported; nothing is fetched automatically."}
          </p>
          <input
            ref={fileRef}
            type="file"
            className="sr-only"
            aria-label={tab === "file" ? "CSV or JSON file" : "Email file"}
            accept={tab === "file" ? ".csv,.json,text/csv,application/json" : ".eml,.mbox,message/rfc822"}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) importFile.mutate(f);
              e.target.value = "";
            }}
          />
          <Button icon={<Upload className="h-4 w-4" aria-hidden />} loading={importFile.isPending} onClick={() => fileRef.current?.click()}>
            Choose file
          </Button>
        </div>
      ) : (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (value.trim()) importParam.mutate();
          }}
        >
          <Field label={def.id === "manual_paste" ? "Job description" : def.label} hint={def.hint}>
            {(id, d) =>
              def.id === "manual_paste" ? (
                <Textarea id={id} aria-describedby={d} className="min-h-[12rem]" value={value} onChange={(e) => setValue(e.target.value)} placeholder="Paste the full posting, including title, company and location" />
              ) : (
                <Input id={id} aria-describedby={d} value={value} onChange={(e) => setValue(e.target.value)} />
              )
            }
          </Field>
          <Button type="submit" loading={importParam.isPending} disabled={!value.trim()}>
            Import
          </Button>
        </form>
      )}
      {result && <ImportSummary result={result} onNavigate={close} />}
    </Modal>
  );
}

function ImportSummary({ result, onNavigate }: { result: ImportResult; onNavigate: () => void }) {
  return (
    <div className="rounded border border-border p-3" role="status">
      <p className="font-medium">
        {result.counts.created} new · {result.counts.updated} updated · {result.counts.failed} failed
      </p>
      <ul className="mt-2 max-h-40 space-y-1 overflow-auto">
        {result.created.map((j) => (
          <li key={j.id}>
            <Link to={`/jobs/${j.id}`} onClick={onNavigate} className="text-primary hover:underline">
              {j.title} — {j.company}
            </Link>
            {j.potential_duplicate && (
              <Badge tone="warning" className="ml-2">
                possible duplicate
              </Badge>
            )}
          </li>
        ))}
        {result.failed.map((f) => (
          <li key={f.ref} className="text-danger">
            {f.ref}: {f.error}
          </li>
        ))}
      </ul>
    </div>
  );
}
