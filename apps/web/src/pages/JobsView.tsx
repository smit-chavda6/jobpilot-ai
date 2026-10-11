import { useState } from "react";
import { Search, Filter, Plus, ExternalLink, Sparkles, AlertCircle, Building2, MapPin, DollarSign } from "lucide-react";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Card, CardContent } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Modal } from "../components/ui/modal";

export function JobsView() {
  const [searchTerm, setSearchTerm] = useState("");
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [importSource, setImportSource] = useState<"greenhouse" | "url" | "csv" | "email">("greenhouse");

  const sampleJobs = [
    {
      id: "job-1",
      title: "Senior Backend Engineer",
      company: "Stripe",
      location: "San Francisco, CA (Remote)",
      remoteType: "remote",
      salary: "$175,000 - $210,000",
      matchScore: 92,
      confidence: 0.95,
      requiredSkills: ["Python", "FastAPI", "PostgreSQL", "Redis"],
      source: "Greenhouse Public Board",
      sourceUrl: "https://boards.greenhouse.io/stripe/jobs/123",
      fitReason: "Direct match on Python, distributed systems, and API design. Exceeds experience bounds.",
    },
    {
      id: "job-2",
      title: "AI Platform Engineer",
      company: "Anthropic",
      location: "San Francisco, CA",
      remoteType: "hybrid",
      salary: "$200,000 - $260,000",
      matchScore: 88,
      confidence: 0.9,
      requiredSkills: ["Python", "PyTorch", "Kubernetes", "Vector Databases"],
      source: "Lever Public Postings",
      sourceUrl: "https://jobs.lever.co/anthropic/456",
      fitReason: "Strong vector search and LLM orchestration alignment. Mentions Kubernetes preferred.",
    },
    {
      id: "job-3",
      title: "Staff Software Engineer - Infrastructure",
      company: "Datadog",
      location: "New York, NY (Remote)",
      remoteType: "remote",
      salary: "$190,000 - $230,000",
      matchScore: 84,
      confidence: 0.85,
      requiredSkills: ["Go", "Python", "Distributed Systems", "PostgreSQL"],
      source: "User Paste / Import",
      sourceUrl: null,
      fitReason: "High architecture overlap. Soft match on secondary language requirements.",
    },
  ];

  const filteredJobs = sampleJobs.filter(
    (j) =>
      j.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      j.company.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-200/60 dark:border-slate-800">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Jobs & Discovery</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Ingest listings through permitted sources or manual import. Two-stage deterministic scoring.
          </p>
        </div>
        <Button onClick={() => setIsImportModalOpen(true)}>
          <Plus className="w-4 h-4 mr-1.5" /> Import New Job
        </Button>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
          <Input
            className="pl-9"
            placeholder="Search by title, company, or tech stack..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <Button variant="outline" className="shrink-0">
          <Filter className="w-4 h-4 mr-1.5" /> Filters
        </Button>
      </div>

      {/* Jobs List */}
      <div className="space-y-4">
        {filteredJobs.map((job) => (
          <Card key={job.id} className="hover:border-indigo-300 dark:hover:border-indigo-800 transition-all">
            <CardContent className="p-6">
              <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                <div className="space-y-2 flex-1">
                  <div className="flex items-center gap-3 flex-wrap">
                    <h3 className="font-bold text-lg text-slate-900 dark:text-slate-100">{job.title}</h3>
                    <Badge variant="secondary" className="font-semibold text-xs">
                      <Building2 className="w-3 h-3 mr-1" /> {job.company}
                    </Badge>
                    <Badge variant="outline" className="capitalize text-xs">
                      {job.remoteType}
                    </Badge>
                  </div>

                  <div className="flex items-center gap-4 text-xs text-slate-500 dark:text-slate-400 flex-wrap">
                    <span className="flex items-center gap-1">
                      <MapPin className="w-3.5 h-3.5" /> {job.location}
                    </span>
                    <span className="flex items-center gap-1">
                      <DollarSign className="w-3.5 h-3.5" /> {job.salary}
                    </span>
                    <span className="text-slate-400">via {job.source}</span>
                  </div>

                  <p className="text-xs text-slate-600 dark:text-slate-300 bg-slate-50 dark:bg-slate-800/50 p-2.5 rounded-lg border border-slate-200/50 dark:border-slate-800">
                    <strong className="text-indigo-600 dark:text-indigo-400">Explainable Match: </strong>
                    {job.fitReason}
                  </p>

                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {job.requiredSkills.map((s) => (
                      <span
                        key={s}
                        className="text-[11px] px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-medium"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Score and CTAs */}
                <div className="flex flex-col sm:items-end justify-between shrink-0 gap-3 border-t md:border-t-0 pt-3 md:pt-0">
                  <div className="text-right">
                    <div className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-extrabold text-2xl">
                      <Sparkles className="w-5 h-5 fill-emerald-500/20" /> {job.matchScore}%
                    </div>
                    <span className="text-[10px] text-slate-400 font-medium">Confidence: {job.confidence * 100}%</span>
                  </div>

                  <div className="flex items-center gap-2">
                    {job.sourceUrl && (
                      <a
                        href={job.sourceUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="p-2 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
                        title="View original posting"
                      >
                        <ExternalLink className="w-4 h-4" />
                      </a>
                    )}
                    <Button size="sm" variant="primary">
                      Tailor Application
                    </Button>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Permitted Ingestion Modal */}
      <Modal
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
        title="Import Job Posting"
        description="Compliance-first ingestion: Only permitted APIs or direct user uploads are supported."
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-2 text-xs">
            <button
              onClick={() => setImportSource("greenhouse")}
              className={`p-2.5 rounded-xl border text-left font-medium transition-colors ${
                importSource === "greenhouse"
                  ? "border-indigo-600 bg-indigo-50/50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300"
                  : "border-slate-200 dark:border-slate-800 hover:bg-slate-50"
              }`}
            >
              Public ATS Board
            </button>
            <button
              onClick={() => setImportSource("url")}
              className={`p-2.5 rounded-xl border text-left font-medium transition-colors ${
                importSource === "url"
                  ? "border-indigo-600 bg-indigo-50/50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300"
                  : "border-slate-200 dark:border-slate-800 hover:bg-slate-50"
              }`}
            >
              Direct URL / Paste
            </button>
            <button
              onClick={() => setImportSource("csv")}
              className={`p-2.5 rounded-xl border text-left font-medium transition-colors ${
                importSource === "csv"
                  ? "border-indigo-600 bg-indigo-50/50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300"
                  : "border-slate-200 dark:border-slate-800 hover:bg-slate-50"
              }`}
            >
              CSV / JSON File
            </button>
            <button
              onClick={() => setImportSource("email")}
              className={`p-2.5 rounded-xl border text-left font-medium transition-colors ${
                importSource === "email"
                  ? "border-indigo-600 bg-indigo-50/50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300"
                  : "border-slate-200 dark:border-slate-800 hover:bg-slate-50"
              }`}
            >
              Email Alert (.eml)
            </button>
          </div>

          <div className="space-y-3 pt-2">
            {importSource === "greenhouse" && (
              <Input
                label="ATS Board Identifier / Company Slug"
                placeholder="e.g. stripe, figma, datadog"
              />
            )}
            {importSource === "url" && (
              <Input
                label="Job Listing URL (SSRF Protected)"
                placeholder="https://company.com/careers/posting-123"
              />
            )}
            {(importSource === "csv" || importSource === "email") && (
              <div className="border-2 border-dashed border-slate-300 dark:border-slate-700 rounded-xl p-6 text-center text-xs text-slate-500">
                Click to browse or drop {importSource === "csv" ? ".csv or .json" : ".eml"} file here
              </div>
            )}
          </div>

          <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-800 text-[11px] text-slate-500 flex items-start gap-1.5">
            <AlertCircle className="w-3.5 h-3.5 mt-0.5 text-slate-400 shrink-0" />
            <span>
              All imports are automatically sanitized and deduped using fingerprint hashing.
            </span>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={() => setIsImportModalOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={() => setIsImportModalOpen(false)}>
              Run Ingestion Pipeline
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
