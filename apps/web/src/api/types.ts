/**
 * Response types for the JobPilot API. Request bodies are typed from the generated OpenAPI
 * schema (`npm run gen:api` -> src/api/schema.d.ts); responses are hand-written here because
 * most endpoints return documented dict payloads (see docs/api.md).
 */

export interface User {
  id: string;
  email: string;
  email_verified: boolean;
}

export type FactStatus = "candidate" | "confirmed" | "rejected";

export interface Fact {
  id: string;
  category: string;
  text: string;
  attributes: Record<string, unknown>;
  source: "resume" | "manual" | string;
  status: FactStatus;
  resume_id: string | null;
  confirmed_at: string | null;
  created_at: string;
}

export interface Profile {
  full_name: string;
  headline: string;
  location: string;
  phone: string;
  years_experience: number | null;
  education_level: string | null;
  target_titles: string[];
  preferred_locations: string[];
  remote_preference: string;
  employment_types: string[];
  min_salary: number | null;
  needs_sponsorship: boolean | null;
  blocked_companies: string[];
  blocked_keywords: string[];
  experience_filter_mode: "soft" | "hard";
  onboarding_step: number;
  onboarding_completed: boolean;
  version: number;
}

export interface ResumeUpload {
  resume_id: string;
  parse_status: string;
  parse_error: string | null;
  facts: Fact[];
  suggestions: {
    contact?: { name?: string; email?: string; phone?: string };
    estimated_years_experience?: number | null;
    detected_education_level?: string | null;
    generator?: string;
  };
}

export interface ResumeFile {
  id: string;
  filename: string;
  size_bytes: number;
  parse_status: string;
  parse_error: string | null;
  created_at: string;
}

export interface Consents {
  consents: Record<string, { granted: boolean; at: string; provider?: string }>;
  ai_provider: string;
  data_sent_to_provider: string[];
}

export type RecommendedAction = "apply" | "apply_after_tailoring" | "research_first" | "skip";

export interface MatchSummary {
  score: number;
  confidence: number;
  eligible: boolean;
  recommended_action: RecommendedAction;
}

export interface JobSummary {
  id: string;
  title: string;
  company: string;
  location: string;
  remote_policy: string;
  employment_type: string;
  source: string;
  url: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  verification_status: string;
  potential_duplicate_of: string | null;
  archived: boolean;
  is_demo: boolean;
  created_at: string;
  scam_level: "none" | "low" | "medium" | "high";
  match: MatchSummary | null;
}

export interface ScamSignal {
  code: string;
  severity: string;
  evidence: string;
  message: string;
}

export interface ScamReport {
  level: "none" | "low" | "medium" | "high";
  confidence: number;
  summary: string;
  signals: ScamSignal[];
}

export interface ScoreComponent {
  value: number | null;
  status: "known" | "unknown" | string;
  weight: number;
  contribution: number;
  detail: string;
}

export interface MatchDetail {
  breakdown: {
    components: Record<string, ScoreComponent>;
    filters: { name: string; passed: boolean; reason: string }[];
  };
  explanation: {
    fit_reasons: string[];
    matched_skills: string[];
    missing_or_uncertain: string[];
    projects_to_highlight: string[];
    questions_to_investigate: string[];
    recommended_action: RecommendedAction;
  };
  config_snapshot: Record<string, unknown>;
  highlight_facts: { id: string; text: string }[];
  scored_at: string;
}

export interface JobDetail extends JobSummary {
  description_html: string;
  description_text: string;
  required_skills: string[];
  preferred_skills: string[];
  min_years: number | null;
  education_req: string | null;
  sponsorship: string;
  contact_email: string | null;
  scam_report: ScamReport;
  last_seen_at: string | null;
  posted_at: string | null;
  application_id: string | null;
  duplicate_of: { id: string; title: string; company: string; source: string } | null;
  match_detail: MatchDetail | null;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface ImportResult {
  created: { id: string; title: string; company: string; potential_duplicate: boolean }[];
  updated: { id: string; title: string; company: string }[];
  failed: { ref: string; stage: string; error: string }[];
  counts: { created: number; updated: number; failed: number };
}

export interface FailedImport {
  id: string;
  source: string;
  input_ref: string;
  stage: string;
  error: string;
  created_at: string;
}

export interface Source {
  id: string;
  name: string;
  enabled: boolean;
  capabilities: Record<string, boolean>;
  compliance: { tos_url: string; reviewed_on: string; allowed_methods: string[]; notes: string };
}

export interface DisabledSource {
  id: string;
  name: string;
  reason: string;
  manual_path: string;
  tos_url: string;
  reviewed_on: string;
}

export interface SavedFilter {
  name: string;
  params: Record<string, string>;
}

export interface DocItem {
  id: string;
  section: string;
  kind: "claim" | "framing";
  text: string;
  supporting_fact_ids: string[];
  group: string;
}

export interface GroundingReport {
  passed: boolean;
  checked: number;
  failed: number;
  items: Record<string, { passed: boolean; reasons: string[] }>;
  validator: string;
}

export interface KeywordReport {
  already_supported?: string[];
  adjacent_ask_user?: string[];
  unsupported?: string[];
}

export interface DocumentSummary {
  id: string;
  job_id: string | null;
  kind: "resume" | "cover_letter";
  title: string;
  grounding_report: GroundingReport;
  keyword_report: KeywordReport;
  grounded: boolean;
  generator: string;
  prompt_version: string;
  version: number;
  content_hash: string;
  created_at: string;
  updated_at: string;
}

export interface DocumentDetail extends DocumentSummary {
  content: {
    header: { name: string; headline: string; location: string; email: string; phone: string };
    items: DocItem[];
  };
  diff: {
    status: "unchanged" | "moved" | "modified" | "added" | "removed";
    section: string;
    before: string | null;
    after: string | null;
    provenance: { fact_id: string; text: string }[];
  }[];
  facts: Fact[];
}

export type AppStatus =
  | "saved"
  | "tailoring"
  | "ready_for_review"
  | "awaiting_approval"
  | "approved"
  | "handoff_opened"
  | "awaiting_user_confirmation"
  | "submitted_confirmed"
  | "interviewing"
  | "offer"
  | "accepted"
  | "rejected"
  | "withdrawn"
  | "declined"
  | "ghosted";

export interface ApplicationSummary {
  id: string;
  job_id: string;
  status: AppStatus;
  resume_doc_id: string | null;
  cover_letter_doc_id: string | null;
  adapter_level: string;
  notes: string;
  submitted_at: string | null;
  last_status_at: string;
  created_at: string;
  version: number;
  is_demo: boolean;
  allowed_moves: AppStatus[];
  job: { id: string; title: string; company: string; url: string | null; location: string; source: string };
}

export interface Activity {
  id: string;
  action: string;
  from: string | null;
  to: string | null;
  actor: string;
  detail: Record<string, unknown>;
  at: string;
}

export interface ScreeningAnswer {
  id: string;
  question: string;
  category: "answerable_from_verified_facts" | "needs_user_input" | "sensitive_legal" | string;
  suggested_answer: string | null;
  supporting_fact_ids: string[];
  answer: string | null;
  answered_by_user: boolean;
}

export interface Reminder {
  id: string;
  due_at: string;
  message: string;
  done: boolean;
  application_id?: string;
}

export interface PreflightCheck {
  name: string;
  ok: boolean;
  blocking: boolean;
  message: string;
}

export interface ApplicationDetail extends ApplicationSummary {
  activity: Activity[];
  screening: ScreeningAnswer[];
  approvals: {
    id: string;
    payload_hash: string;
    approved_at: string;
    invalidated_at: string | null;
    invalidated_reason: string | null;
  }[];
  preflight: { ok: boolean; checks: PreflightCheck[] };
  approval_payload: Record<string, unknown>;
  approval_payload_hash: string;
  reminders: Reminder[];
}

export interface ApplicationsPage extends Page<ApplicationSummary> {
  columns: Record<string, AppStatus[]>;
}

export interface TriageItem {
  id: string;
  message_id: string;
  subject: string;
  sender: string;
  received_at: string | null;
  classification: string;
  confidence: number;
  evidence: string;
  snippet: string;
  application_id: string | null;
  suggested_status: string | null;
  review_status: "pending" | "accepted" | "dismissed" | "info" | string;
  scam_report: ScamReport;
  draft_reply: string | null;
  created_at: string;
}

export interface BankQuestion {
  type: string;
  question: string;
  skills: string[];
  fact_id?: string;
  id?: string;
}

export interface Star {
  question: string;
  supporting_fact_ids: string[];
  situation: string | null;
  task: string | null;
  action: string | null;
  result: string | null;
  note?: string;
}

export interface Feedback {
  scores: Record<"relevance" | "structure" | "specificity" | "clarity", number>;
  overall: number;
  tips: string[];
  word_count: number;
  star_elements: Record<string, boolean>;
}

export interface PrepSession {
  id: string;
  job_id: string | null;
  questions: (BankQuestion & { id: string })[];
  answers: Record<string, string>;
  feedback: Record<string, Feedback>;
  overall_score: number | null;
  completed: boolean;
  created_at: string;
}

export interface Rate {
  n: number;
  successes: number;
  rate: number | null;
  ci_low: number | null;
  ci_high: number | null;
  insufficient_data: boolean;
  min_n: number;
}

export interface Analytics {
  totals: { jobs: number; applications: number; submitted: number; demo_applications: number; include_demo: boolean };
  by_status: Record<string, number>;
  response_rate: Rate;
  interview_rate: Rate;
  offer_rate: Rate;
  funnel: { stage: string; count: number; drop_off: number | null }[];
  time_to_response: { n: number; median_days: number | null; buckets: { bucket: string; count: number }[] };
  by_source: { source: string; response_rate: Rate }[];
  score_band_vs_interview: { band: string; interview_rate: Rate }[];
  weekly_submissions: { week: string; count: number }[];
  min_n: number;
  note: string;
}

export interface Settings {
  ai_daily_token_budget: number | null;
  notify_reminders: boolean;
  notify_triage: boolean;
  retention_days: number | null;
  adapter_flags: Record<string, boolean>;
  ai: { provider: string; used_last_24h: number; budget: number };
}

export interface Notification {
  id: string;
  kind: string;
  message: string;
  link: string | null;
  read: boolean;
  created_at: string;
}

export interface Dashboard {
  onboarding_completed: boolean;
  counts: {
    jobs: number;
    applications: number;
    candidate_facts: number;
    confirmed_facts: number;
    pending_triage: number;
    unread_notifications: number;
  };
  applications_by_status: Record<string, number>;
  top_matches: {
    id: string;
    title: string;
    company: string;
    score: number;
    confidence: number;
    recommended_action: RecommendedAction;
    is_demo: boolean;
  }[];
  upcoming_reminders: Reminder[];
}

export interface Integrations {
  connected: { id: string; provider: string; scopes: string[]; status: string }[];
  available: { provider: string; status: string; scopes: string[]; note: string }[];
}
