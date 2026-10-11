import { useState } from "react";
import { Check, X, ShieldCheck, Download, Plus, Sparkles } from "lucide-react";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/card";
import { Modal } from "../components/ui/modal";
import { Input } from "../components/ui/input";

interface Fact {
  id: string;
  text: string;
  category: string;
  status: "candidate" | "confirmed" | "rejected";
  source: string;
}

export function ResumeStudioView() {
  const [activeTab, setActiveTab] = useState<"candidate" | "confirmed" | "rejected">("candidate");
  const [isAddFactModalOpen, setIsAddFactModalOpen] = useState(false);
  const [newFactText, setNewFactText] = useState("");

  const [facts, setFacts] = useState<Fact[]>([
    {
      id: "fact-01",
      text: "Architected real-time event streaming pipeline using Python, Kafka, and Redis reducing ingestion latency by 45%.",
      category: "experience",
      status: "candidate",
      source: "Uploaded Resume (PDF)",
    },
    {
      id: "fact-02",
      text: "Led migration of monolith to 12 async FastAPI microservices handling 20,000 requests per second.",
      category: "experience",
      status: "candidate",
      source: "Uploaded Resume (PDF)",
    },
    {
      id: "fact-03",
      text: "Graduated B.S. in Computer Science with Honors from UC Berkeley, 2018–2022.",
      category: "education",
      status: "confirmed",
      source: "Manual Entry",
    },
    {
      id: "fact-04",
      text: "Designed open-source vector similarity search index with HNSW in pgvector and PostgreSQL 16.",
      category: "project",
      status: "confirmed",
      source: "GitHub Import",
    },
  ]);

  const confirmFact = (id: string) => {
    setFacts((prev) => prev.map((f) => (f.id === id ? { ...f, status: "confirmed" } : f)));
  };

  const rejectFact = (id: string) => {
    setFacts((prev) => prev.map((f) => (f.id === id ? { ...f, status: "rejected" } : f)));
  };

  const addManualFact = () => {
    if (!newFactText.trim()) return;
    const newFact: Fact = {
      id: `fact-${Date.now()}`,
      text: newFactText,
      category: "experience",
      status: "confirmed",
      source: "Manual Verified Fact",
    };
    setFacts((prev) => [newFact, ...prev]);
    setNewFactText("");
    setIsAddFactModalOpen(false);
  };

  const filteredFacts = facts.filter((f) => f.status === activeTab);

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-200/60 dark:border-slate-800">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Resume Studio & Atomic Facts</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Section 6 Core Differentiator: Nothing is usable downstream until confirmed by you.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setIsAddFactModalOpen(true)}>
            <Plus className="w-4 h-4 mr-1.5" /> Add Atomic Fact
          </Button>
          <Button size="sm">
            <Download className="w-4 h-4 mr-1.5" /> Export Clean PDF
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Atomic Fact Verification Manager */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center gap-2 border-b border-slate-200 dark:border-slate-800 pb-2">
            <button
              onClick={() => setActiveTab("candidate")}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                activeTab === "candidate"
                  ? "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              Candidates for Review ({facts.filter((f) => f.status === "candidate").length})
            </button>
            <button
              onClick={() => setActiveTab("confirmed")}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                activeTab === "confirmed"
                  ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              Confirmed Ground Truth ({facts.filter((f) => f.status === "confirmed").length})
            </button>
            <button
              onClick={() => setActiveTab("rejected")}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                activeTab === "rejected"
                  ? "bg-slate-200 text-slate-800 dark:bg-slate-800 dark:text-slate-300"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              Rejected ({facts.filter((f) => f.status === "rejected").length})
            </button>
          </div>

          <div className="space-y-3">
            {filteredFacts.map((fact) => (
              <Card key={fact.id} className="hover:border-slate-300 transition-colors">
                <CardContent className="p-4 flex items-start justify-between gap-4">
                  <div className="space-y-1.5 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-slate-400 font-semibold">{fact.id}</span>
                      <Badge variant="outline" className="text-[10px] uppercase">
                        {fact.category}
                      </Badge>
                      <span className="text-[11px] text-slate-400">from {fact.source}</span>
                    </div>
                    <p className="text-sm font-medium text-slate-800 dark:text-slate-200 leading-relaxed">
                      {fact.text}
                    </p>
                  </div>

                  {fact.status === "candidate" && (
                    <div className="flex items-center gap-1.5 shrink-0">
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 w-8 p-0 text-rose-600 hover:bg-rose-50 border-rose-200"
                        onClick={() => rejectFact(fact.id)}
                        title="Reject Fact"
                      >
                        <X className="w-4 h-4" />
                      </Button>
                      <Button
                        size="sm"
                        variant="primary"
                        className="h-8 w-8 p-0 bg-emerald-600 hover:bg-emerald-700"
                        onClick={() => confirmFact(fact.id)}
                        title="Confirm Fact"
                      >
                        <Check className="w-4 h-4" />
                      </Button>
                    </div>
                  )}

                  {fact.status === "confirmed" && (
                    <Badge variant="success" className="shrink-0 text-[10px] gap-1">
                      <ShieldCheck className="w-3 h-3" /> Confirmed
                    </Badge>
                  )}
                </CardContent>
              </Card>
            ))}

            {filteredFacts.length === 0 && (
              <div className="p-8 text-center border border-dashed border-slate-200 dark:border-slate-800 rounded-xl text-slate-400 text-xs">
                No facts found in this state.
              </div>
            )}
          </div>
        </div>

        {/* Tailored Bullet Grounding Inspector */}
        <div className="space-y-4">
          <Card className="border-indigo-200/80 bg-indigo-50/20 dark:bg-slate-900">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-indigo-500" /> Grounding Inspector
              </CardTitle>
              <CardDescription className="text-xs">
                Generated bullets must cite verified facts. Entities and quantifiers verified deterministically.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-xs">
              <div className="p-3 rounded-xl bg-white dark:bg-slate-800 border border-slate-200/70 dark:border-slate-700 space-y-2">
                <span className="font-semibold text-slate-900 dark:text-slate-100 block">
                  Tailored Bullet for Stripe:
                </span>
                <p className="text-slate-700 dark:text-slate-300 leading-relaxed">
                  "Designed high-concurrency event stream pipelines with Python and Redis, improving latency by 45%."
                </p>
                <div className="pt-2 border-t border-slate-100 dark:border-slate-700 flex items-center justify-between text-[11px]">
                  <span className="text-slate-400">Cited Fact:</span>
                  <Badge variant="default" className="text-[10px]">
                    fact-01
                  </Badge>
                </div>
                <div className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 text-[11px] font-semibold">
                  <ShieldCheck className="w-3.5 h-3.5" /> All entities & metrics verified in profile
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Add Fact Modal */}
      <Modal
        isOpen={isAddFactModalOpen}
        onClose={() => setIsAddFactModalOpen(false)}
        title="Add Verified Fact"
        description="Add a specific, factual claim about your accomplishments, metrics, or credentials."
      >
        <div className="space-y-4">
          <Input
            label="Claim Text"
            placeholder="Built X using Y at Z, improving metric by N%"
            value={newFactText}
            onChange={(e) => setNewFactText(e.target.value)}
          />
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={() => setIsAddFactModalOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={addManualFact}>
              Add & Confirm Fact
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
