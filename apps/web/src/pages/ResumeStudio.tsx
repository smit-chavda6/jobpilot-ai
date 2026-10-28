import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowDown, ArrowLeft, ArrowUp, CheckCircle2, Download, Plus, Save, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { api, ApiError, errorMessage } from "@/api/client";
import type { DocItem, DocumentDetail, Fact } from "@/api/types";
import { useToast } from "@/components/Toast";
import { Badge, Button, Card, CardTitle, cn, Modal, QueryView, Select, Textarea } from "@/components/ui";
import { humanize } from "@/lib/format";

export default function ResumeStudio() {
  const { docId = "" } = useParams();
  const q = useQuery({ queryKey: ["document", docId], queryFn: () => api.get<DocumentDetail>(`/api/documents/${docId}`) });
  return (
    <>
      <Link to="/documents" className="mb-4 inline-flex items-center gap-1 text-sm text-subtle hover:text-fg">
        <ArrowLeft className="h-4 w-4" aria-hidden /> All documents
      </Link>
      <QueryView query={q} loadingLabel="Loading document">
        {(doc) => <Studio key={`${doc.id}-${doc.version}`} doc={doc} />}
      </QueryView>
    </>
  );
}

type Tab = "edit" | "diff" | "keywords";

function Studio({ doc }: { doc: DocumentDetail }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [items, setItems] = useState<DocItem[]>(doc.content.items);
  const [tab, setTab] = useState<Tab>("edit");
  const [citing, setCiting] = useState<number | null>(null);
  const dirty = JSON.stringify(items) !== JSON.stringify(doc.content.items);
  const facts = useMemo(() => Object.fromEntries(doc.facts.map((f) => [f.id, f])), [doc.facts]);

  // Autosave a local draft so an accidental navigation doesn't lose edits.
  const draftKey = `jp-draft-${doc.id}-${doc.version}`;
  useEffect(() => {
    try {
      const saved = localStorage.getItem(draftKey);
      if (saved) setItems(JSON.parse(saved) as DocItem[]);
    } catch {
      /* ignore corrupt draft */
    }
  }, [draftKey]);
  useEffect(() => {
    try {
      if (dirty) localStorage.setItem(draftKey, JSON.stringify(items));
      else localStorage.removeItem(draftKey);
    } catch {
      /* storage unavailable */
    }
  }, [items, dirty, draftKey]);

  const save = useMutation({
    mutationFn: () =>
      api.put<DocumentDetail>(`/api/documents/${doc.id}`, { items: items.map(({ id, section, kind, text, supporting_fact_ids, group }) => ({ id, section, kind, text, supporting_fact_ids, group })) }, { headers: { "If-Match": `W/"${doc.version}"` } }),
    onSuccess: (d) => {
      try {
        localStorage.removeItem(draftKey);
      } catch {
        /* ignore */
      }
      void qc.invalidateQueries({ queryKey: ["document", doc.id] });
      void qc.invalidateQueries({ queryKey: ["documents"] });
      void qc.invalidateQueries({ queryKey: ["application"] });
      toast.success(d.grounded ? "Saved — all items grounded" : `Saved — ${d.grounding_report.failed} item(s) fail grounding and block export`);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 412) toast.error("This document changed in another tab. Reload to see the latest version.");
      else toast.error(errorMessage(e));
    },
  });
  const exportDoc = useMutation({
    mutationFn: (format: "pdf" | "docx") => api.download(`/api/documents/${doc.id}/export?format=${format}`, `${doc.title.replace(/[^A-Za-z0-9_-]+/g, "_").slice(0, 60)}.${format}`),
    onError: (e) => toast.error(errorMessage(e)),
  });

  const update = (i: number, patch: Partial<DocItem>) => setItems((xs) => xs.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const move = (i: number, d: -1 | 1) =>
    setItems((xs) => {
      const n = [...xs];
      const t = n[i + d];
      if (!t) return xs;
      n[i + d] = n[i]!;
      n[i] = t;
      return n;
    });
  const sections = [...new Set(items.map((i) => i.section))];
  const report = doc.grounding_report;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{doc.title}</h1>
          <p className="text-sm text-subtle">
            v{doc.version} · {doc.generator} · prompt {doc.prompt_version} · validator {report.validator}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button icon={<Save className="h-4 w-4" aria-hidden />} disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>
            Save & re-check
          </Button>
          <Button variant="secondary" icon={<Download className="h-4 w-4" aria-hidden />} disabled={!doc.grounded || dirty} loading={exportDoc.isPending && exportDoc.variables === "pdf"} onClick={() => exportDoc.mutate("pdf")}>
            PDF
          </Button>
          <Button variant="secondary" icon={<Download className="h-4 w-4" aria-hidden />} disabled={!doc.grounded || dirty} loading={exportDoc.isPending && exportDoc.variables === "docx"} onClick={() => exportDoc.mutate("docx")}>
            DOCX
          </Button>
        </div>
      </div>

      <div
        role="status"
        className={cn("flex items-center gap-2 rounded border p-3 text-sm", doc.grounded ? "border-success/40 bg-success/5" : "border-danger/40 bg-danger/5")}
      >
        {doc.grounded ? <CheckCircle2 className="h-4 w-4 text-success" aria-hidden /> : <AlertTriangle className="h-4 w-4 text-danger" aria-hidden />}
        {doc.grounded
          ? `All ${report.checked} items are supported by your confirmed facts.`
          : `${report.failed} of ${report.checked} items aren't supported by the facts they cite. Export is blocked until they're fixed or removed.`}
        {dirty && <span className="ml-auto text-warning">Unsaved changes (draft kept locally)</span>}
      </div>

      <div role="tablist" aria-label="Studio views" className="flex gap-1 border-b border-border">
        {(["edit", "diff", "keywords"] as Tab[])
          .filter((t) => t !== "diff" || doc.kind === "resume")
          .filter((t) => t !== "keywords" || doc.kind === "resume")
          .map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={cn("-mb-px border-b-2 px-4 py-2 text-sm", tab === t ? "border-primary font-medium text-primary" : "border-transparent text-subtle hover:text-fg")}>
              {t === "edit" ? "Editor" : t === "diff" ? "Diff & provenance" : "Keywords"}
            </button>
          ))}
      </div>

      {tab === "edit" && (
        <div className="space-y-6">
          {sections.map((section) => (
            <Card key={section}>
              <CardTitle>{humanize(section)}</CardTitle>
              <ul className="space-y-3">
                {items.map((item, i) =>
                  item.section !== section ? null : (
                    <li key={item.id || i} className={cn("rounded border p-3", report.items[item.id]?.passed === false ? "border-danger/50" : "border-border")}>
                      {item.group && <p className="mb-1 text-xs font-medium text-subtle">{item.group}</p>}
                      <Textarea aria-label={`Item ${i + 1} text`} className="min-h-[3.5rem]" value={item.text} onChange={(e) => update(i, { text: e.target.value })} maxLength={800} />
                      {report.items[item.id]?.passed === false && !dirty && (
                        <ul className="mt-2 space-y-1 text-xs text-danger" aria-label="Grounding failures">
                          {report.items[item.id]!.reasons.map((r) => (
                            <li key={r} className="flex gap-1">
                              <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden /> {r}
                            </li>
                          ))}
                        </ul>
                      )}
                      <div className="mt-2 flex flex-wrap items-center gap-1">
                        {item.kind === "framing" ? (
                          <Badge>framing sentence</Badge>
                        ) : (
                          <>
                            <span className="text-xs text-subtle">Cites:</span>
                            {item.supporting_fact_ids.length === 0 && <Badge tone="danger">no facts — will fail</Badge>}
                            {item.supporting_fact_ids.map((fid) => (
                              <span key={fid} className="inline-flex items-center gap-1 rounded-sm bg-muted px-1.5 py-0.5 text-xs" title={facts[fid]?.text ?? "Fact not confirmed or removed"}>
                                <span className="max-w-[16rem] truncate">{facts[fid]?.text ?? "Unknown fact"}</span>
                                <button aria-label="Remove citation" onClick={() => update(i, { supporting_fact_ids: item.supporting_fact_ids.filter((x) => x !== fid) })}>
                                  <X className="h-3 w-3" aria-hidden />
                                </button>
                              </span>
                            ))}
                            <Button size="sm" variant="ghost" onClick={() => setCiting(i)}>
                              + cite fact
                            </Button>
                          </>
                        )}
                        <span className="flex-1" />
                        <Button size="sm" variant="ghost" aria-label="Move up" disabled={i === 0} onClick={() => move(i, -1)}>
                          <ArrowUp className="h-4 w-4" aria-hidden />
                        </Button>
                        <Button size="sm" variant="ghost" aria-label="Move down" disabled={i === items.length - 1} onClick={() => move(i, 1)}>
                          <ArrowDown className="h-4 w-4" aria-hidden />
                        </Button>
                        <Button size="sm" variant="ghost" aria-label="Remove item" onClick={() => setItems((xs) => xs.filter((_, j) => j !== i))}>
                          <Trash2 className="h-4 w-4" aria-hidden />
                        </Button>
                      </div>
                    </li>
                  ),
                )}
              </ul>
              <Button
                size="sm"
                variant="secondary"
                className="mt-3"
                icon={<Plus className="h-4 w-4" aria-hidden />}
                onClick={() => {
                  setItems((xs) => [...xs, { id: "", section, kind: "claim", text: "", supporting_fact_ids: [], group: "" }]);
                  setCiting(items.length);
                }}
              >
                Add item from a fact
              </Button>
            </Card>
          ))}
        </div>
      )}

      {tab === "diff" && <DiffView doc={doc} />}
      {tab === "keywords" && <KeywordsView doc={doc} />}

      <CiteDialog
        open={citing !== null}
        facts={doc.facts}
        onClose={() => setCiting(null)}
        onPick={(f) => {
          if (citing === null) return;
          const item = items[citing];
          if (!item) return;
          update(citing, {
            supporting_fact_ids: item.supporting_fact_ids.includes(f.id) ? item.supporting_fact_ids : [...item.supporting_fact_ids, f.id],
            text: item.text.trim() ? item.text : f.text,
          });
          setCiting(null);
        }}
      />
    </div>
  );
}

function CiteDialog({ open, facts, onClose, onPick }: { open: boolean; facts: Fact[]; onClose: () => void; onPick: (f: Fact) => void }) {
  const [cat, setCat] = useState("");
  const list = facts.filter((f) => !cat || f.category === cat);
  return (
    <Modal open={open} title="Cite a confirmed fact" onClose={onClose} footer={<Button variant="secondary" onClick={onClose}>Cancel</Button>}>
      <Select aria-label="Filter by category" value={cat} onChange={(e) => setCat(e.target.value)}>
        <option value="">All categories</option>
        {[...new Set(facts.map((f) => f.category))].map((c) => (
          <option key={c} value={c}>
            {humanize(c)}
          </option>
        ))}
      </Select>
      <ul className="max-h-80 space-y-1 overflow-auto">
        {list.map((f) => (
          <li key={f.id}>
            <button className="w-full rounded p-2 text-left hover:bg-muted" onClick={() => onPick(f)}>
              <Badge className="mr-2">{f.category}</Badge>
              {f.text}
            </button>
          </li>
        ))}
        {list.length === 0 && <li className="text-subtle">No confirmed facts.</li>}
      </ul>
    </Modal>
  );
}

function DiffView({ doc }: { doc: DocumentDetail }) {
  return (
    <Card>
      <p className="mb-3 text-sm text-subtle">Compared with the first generated version. Hover or focus a line to see the facts it is based on.</p>
      <ul className="space-y-1 font-mono text-sm">
        {doc.diff.map((row, i) => (
          <li
            key={i}
            tabIndex={0}
            title={row.provenance.map((p) => `• ${p.text}`).join("\n") || "No supporting facts"}
            className={cn(
              "rounded px-2 py-1",
              row.status === "added" && "bg-success/10",
              row.status === "removed" && "bg-danger/10 line-through",
              row.status === "modified" && "bg-warning/10",
              row.status === "moved" && "bg-info/10",
            )}
          >
            <span className="mr-2 inline-block w-4 text-subtle" aria-label={row.status}>
              {({ added: "+", removed: "−", modified: "~", moved: "↕" } as Record<string, string>)[row.status] ?? " "}
            </span>
            <span>{row.after ?? row.before}</span>
            {row.provenance.length > 0 && <span className="sr-only">. Based on: {row.provenance.map((p) => p.text).join("; ")}</span>}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function KeywordsView({ doc }: { doc: DocumentDetail }) {
  const k = doc.keyword_report;
  const Group = ({ title, items, tone, note }: { title: string; items?: string[]; tone: "success" | "warning" | "danger"; note: string }) => (
    <div>
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="mb-2 text-xs text-subtle">{note}</p>
      <div className="flex flex-wrap gap-1">{items?.length ? items.map((s) => <Badge key={s} tone={tone}>{s}</Badge>) : <span className="text-sm text-subtle">None</span>}</div>
    </div>
  );
  return (
    <Card className="grid gap-6 md:grid-cols-3">
      <Group title="Already supported" items={k.already_supported} tone="success" note="Backed by confirmed facts — included automatically." />
      <Group title="Adjacent — ask yourself" items={k.adjacent_ask_user} tone="warning" note="Related to what you've done. Add a fact in Profile only if it's true." />
      <Group title="Unsupported — not added" items={k.unsupported} tone="danger" note="Not in your facts. JobPilot will not add these." />
    </Card>
  );
}
