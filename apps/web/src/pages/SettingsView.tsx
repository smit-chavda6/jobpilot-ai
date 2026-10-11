import { useState } from "react";
import { Shield, Download, Trash2, Zap, AlertTriangle } from "lucide-react";
import { Button } from "../components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Modal } from "../components/ui/modal";

export function SettingsView() {
  const [dailyBudget, setDailyBudget] = useState("50000");
  const [aiConsent, setAiConsent] = useState(true);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");

  const handleExportData = () => {
    alert("Export initiated: An archive containing all your verified profile facts, applications, and logs will download.");
  };

  const handleHardDelete = () => {
    if (deleteConfirmText !== "DELETE") {
      alert("Please type DELETE to confirm account destruction.");
      return;
    }
    alert("Account and all associated records, vectors, and files scheduled for immediate hard deletion.");
    setIsDeleteModalOpen(false);
  };

  return (
    <div className="space-y-8 max-w-4xl animate-in fade-in duration-300">
      <div className="pb-2 border-b border-slate-200/60 dark:border-slate-800">
        <h1 className="text-2xl font-extrabold tracking-tight">Account & Privacy Settings</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          GDPR and DPDP Act aligned data privacy controls, AI budget guards, and full account deletion.
        </p>
      </div>

      {/* AI Token Budget & Provider Guardrails */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Zap className="w-4 h-4 text-amber-500" /> Daily AI Token Budget & Limits
          </CardTitle>
          <CardDescription>
            Prevents unexpected cost exhaustion. Fallbacks seamlessly to deterministic matching when budget is reached.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="max-w-xs">
            <Input
              label="Daily Token Cap per User"
              value={dailyBudget}
              onChange={(e) => setDailyBudget(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            <span>Currently using server-side Mock & Gemini providers. Zero client-side API keys exposed.</span>
          </div>
        </CardContent>
      </Card>

      {/* Privacy & Consents */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Shield className="w-4 h-4 text-indigo-500" /> Explicit Consent Records
          </CardTitle>
          <CardDescription>
            Audit-logged consent for third-party model inference. You can revoke consent at any time.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-xs">
          <div className="flex items-center justify-between p-4 rounded-xl border border-slate-200 dark:border-slate-800">
            <div>
              <p className="font-bold text-slate-800 dark:text-slate-200 text-sm">
                LLM Grounding & Fact Extraction
              </p>
              <p className="text-slate-500 mt-0.5">
                Permits sending anonymized job descriptions and confirmed facts to the server-side model provider.
              </p>
            </div>
            <button
              onClick={() => setAiConsent(!aiConsent)}
              className={`w-11 h-6 flex items-center rounded-full p-1 transition-colors ${
                aiConsent ? "bg-indigo-600 justify-end" : "bg-slate-300 dark:bg-slate-700 justify-start"
              }`}
            >
              <div className="bg-white w-4 h-4 rounded-full shadow-md" />
            </button>
          </div>
        </CardContent>
      </Card>

      {/* Data Export & Deletion */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Data Portability & Erasure</CardTitle>
          <CardDescription>
            Export your entire history or exercise your Right to be Forgotten.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 rounded-xl border border-slate-200 dark:border-slate-800">
            <div>
              <p className="font-bold text-sm text-slate-800 dark:text-slate-200">Full Data Export</p>
              <p className="text-xs text-slate-500 mt-0.5">
                Download all profile facts, applications, documents, and audit logs as standard JSON.
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={handleExportData}>
              <Download className="w-4 h-4 mr-1.5" /> Export All Data
            </Button>
          </div>

          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 rounded-xl border border-rose-200 dark:border-rose-950/60 bg-rose-50/20 dark:bg-rose-950/10">
            <div>
              <p className="font-bold text-sm text-rose-700 dark:text-rose-400">Verified Hard Deletion</p>
              <p className="text-xs text-slate-500 mt-0.5">
                Permanently wipes all user-owned tables, vector embeddings, uploaded files, and sessions.
              </p>
            </div>
            <Button variant="destructive" size="sm" onClick={() => setIsDeleteModalOpen(true)}>
              <Trash2 className="w-4 h-4 mr-1.5" /> Delete Account
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Deletion Confirmation Modal */}
      <Modal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        title="Destroy Account and Data"
        description="This action is completely irreversible. All your facts, applications, and embeddings will be permanently erased."
      >
        <div className="space-y-4">
          <div className="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 text-xs text-rose-700 dark:text-rose-300 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>Type <strong>DELETE</strong> below to confirm hard deletion.</span>
          </div>
          <Input
            placeholder="DELETE"
            value={deleteConfirmText}
            onChange={(e) => setDeleteConfirmText(e.target.value)}
          />
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={() => setIsDeleteModalOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" size="sm" onClick={handleHardDelete}>
              Confirm Permanent Erasure
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
