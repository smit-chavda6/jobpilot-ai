import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errorMessage } from "@/api/client";
import type { Consents, Fact, Profile, ResumeUpload } from "@/api/types";
import { FactReview } from "@/components/domain";
import { BasicsForm, PreferencesForm, useSaveProfile } from "@/components/ProfileForms";
import { useToast } from "@/components/Toast";
import { Button, Card, cn, QueryView, Spinner } from "@/components/ui";

const STEPS = ["Consent", "About you", "Preferences", "Resume", "Confirm facts"];

/** Resumable wizard: the current step is stored on the profile (onboarding_step) after each step. */
export default function Onboarding() {
  const profile = useQuery({ queryKey: ["profile"], queryFn: () => api.get<Profile>("/api/profile") });
  if (profile.isLoading) return <Spinner />;
  if (!profile.data) return <QueryView query={profile}>{() => null}</QueryView>;
  return <Wizard profile={profile.data} />;
}

function Wizard({ profile }: { profile: Profile }) {
  const [step, setStep] = useState(Math.min(Math.max(profile.onboarding_step, 0), STEPS.length - 1));
  const save = useSaveProfile();
  const navigate = useNavigate();
  const go = (n: number) => {
    setStep(n);
    save.mutate({ onboarding_step: n });
  };
  const finish = async () => {
    await save.mutateAsync({ onboarding_step: STEPS.length, onboarding_completed: true });
    navigate("/", { replace: true });
  };

  return (
    <main className="mx-auto max-w-3xl p-4 sm:p-8">
      <div className="mb-6 flex items-center gap-2 text-lg font-semibold">
        <img src="/favicon.svg" alt="" className="h-7 w-7" /> Set up JobPilot
      </div>
      <nav aria-label="Onboarding progress" className="mb-6">
        <ol className="flex flex-wrap gap-2">
          {STEPS.map((s, i) => (
            <li key={s} aria-current={i === step ? "step" : undefined} className="flex items-center gap-2 text-sm">
              <span
                className={cn(
                  "flex h-6 w-6 items-center justify-center rounded-full text-xs",
                  i < step ? "bg-success text-white dark:text-bg" : i === step ? "bg-primary text-primary-fg" : "bg-muted text-subtle",
                )}
              >
                {i < step ? <Check className="h-3.5 w-3.5" aria-hidden /> : i + 1}
              </span>
              <span className={cn(i === step ? "font-medium" : "text-subtle")}>{s}</span>
              {i < STEPS.length - 1 && <span className="text-subtle" aria-hidden>›</span>}
            </li>
          ))}
        </ol>
      </nav>
      <Card className="p-6">
        {step === 0 && <ConsentStep onNext={() => go(1)} />}
        {step === 1 && (
          <>
            <h1 className="mb-1 text-xl font-semibold">About you</h1>
            <p className="mb-4 text-sm text-subtle">Used for matching. You can change this any time in Profile.</p>
            <BasicsForm profile={profile} submitLabel="Continue" extra={{ onboarding_step: 2 }} onSaved={() => setStep(2)} />
          </>
        )}
        {step === 2 && (
          <>
            <h1 className="mb-1 text-xl font-semibold">What are you looking for?</h1>
            <p className="mb-4 text-sm text-subtle">Hard filters remove jobs; everything else only affects the score.</p>
            <PreferencesForm profile={profile} submitLabel="Continue" extra={{ onboarding_step: 3 }} onSaved={() => setStep(3)} />
          </>
        )}
        {step === 3 && <ResumeStep onNext={() => go(4)} />}
        {step === 4 && <ConfirmStep onFinish={() => void finish()} finishing={save.isPending} />}
        {step > 0 && (
          <Button variant="ghost" className="mt-4" onClick={() => go(step - 1)}>
            Back
          </Button>
        )}
      </Card>
    </main>
  );
}

function ConsentStep({ onNext }: { onNext: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const consents = useQuery({ queryKey: ["consents"], queryFn: () => api.get<Consents>("/api/consents") });
  const grant = useMutation({
    mutationFn: (granted: boolean) => api.post("/api/consents", { purpose: "ai_processing", granted }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["consents"] });
      onNext();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const provider = consents.data?.ai_provider ?? "…";
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">How JobPilot uses your data</h1>
      <ul className="list-disc space-y-2 pl-5 text-sm">
        <li>
          You confirm every fact about yourself. Generated resumes and cover letters may only use <strong>confirmed facts</strong>, and every
          claim is checked against them.
        </li>
        <li>
          JobPilot never submits applications or sends emails. You approve each application and press the employer's submit button yourself.
        </li>
        <li>
          Configured AI provider: <strong>{provider}</strong>
          {provider === "mock" ? " (deterministic, runs locally — nothing leaves this server)." : ". Resume text, facts and job descriptions are sent to it when you use AI features."}
        </li>
        <li>You can export or permanently delete all of your data from Settings.</li>
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button loading={grant.isPending && grant.variables === true} onClick={() => grant.mutate(true)}>
          Allow AI processing and continue
        </Button>
        <Button variant="secondary" loading={grant.isPending && grant.variables === false} onClick={() => grant.mutate(false)}>
          Continue without AI
        </Button>
      </div>
      <p className="text-xs text-subtle">Without AI consent, parsing, matching and generation use deterministic rules only.</p>
    </div>
  );
}

function ResumeStep({ onNext }: { onNext: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [result, setResult] = useState<ResumeUpload | null>(null);
  const upload = useMutation({
    mutationFn: (f: File) => api.upload<ResumeUpload>("/api/resumes", f),
    onSuccess: (r) => {
      setResult(r);
      void qc.invalidateQueries({ queryKey: ["facts"] });
      if (r.parse_status !== "parsed") toast.error(r.parse_error ?? "Couldn't parse this file");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Upload your resume</h1>
      <p className="text-sm text-subtle">
        PDF, DOCX or TXT, up to 5 MB. Files are checked (type, size, macros) and stored outside the web root. We extract <em>candidate</em> facts
        for you to confirm on the next step.
      </p>
      <input
        ref={input}
        type="file"
        accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
        className="sr-only"
        aria-label="Resume file"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) upload.mutate(f);
          e.target.value = "";
        }}
      />
      <Button icon={<Upload className="h-4 w-4" aria-hidden />} loading={upload.isPending} onClick={() => input.current?.click()}>
        Choose file
      </Button>
      {result && result.parse_status === "parsed" && (
        <p role="status" className="text-sm text-success">
          Found {result.facts.length} candidate facts.
          {result.suggestions.estimated_years_experience != null && ` Estimated experience: ${result.suggestions.estimated_years_experience} years.`}
        </p>
      )}
      <div className="flex gap-2">
        <Button onClick={onNext} disabled={upload.isPending}>
          {result ? "Review facts" : "Skip — I'll add facts manually"}
        </Button>
      </div>
    </div>
  );
}

function ConfirmStep({ onFinish, finishing }: { onFinish: () => void; finishing: boolean }) {
  const facts = useQuery({ queryKey: ["facts"], queryFn: () => api.get<Fact[]>("/api/facts") });
  const confirmed = facts.data?.filter((f) => f.status === "confirmed").length ?? 0;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Confirm your facts</h1>
      <p className="text-sm text-subtle">
        Only confirmed facts are used for matching and document generation. Reject anything inaccurate; edit anything that needs fixing.
      </p>
      <QueryView query={facts} isEmpty={(d) => d.length === 0} empty={<p className="text-sm text-subtle">No facts yet. You can add them later in Profile.</p>}>
        {(d) => <FactReview facts={d} compact />}
      </QueryView>
      <div className="flex items-center justify-between gap-2 border-t border-border pt-4">
        <span className="text-sm text-subtle">{confirmed} confirmed</span>
        <Button onClick={onFinish} loading={finishing}>
          Finish setup
        </Button>
      </div>
    </div>
  );
}
