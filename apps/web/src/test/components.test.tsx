import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Fact, MatchDetail, ScamReport } from "@/api/types";
import { FactReview, ScamPanel, ScoreBreakdown } from "@/components/domain";
import { mockFetch, renderWithProviders } from "./utils";

afterEach(() => vi.unstubAllGlobals());

const fact = (id: string, status: Fact["status"], text = `Fact ${id}`): Fact => ({
  id,
  category: "experience",
  text,
  attributes: {},
  source: "resume",
  status,
  resume_id: null,
  confirmed_at: null,
  created_at: "2026-01-01T00:00:00Z",
});

describe("FactReview", () => {
  it("warns that unconfirmed facts are unused and confirms all in one call", async () => {
    const calls = mockFetch((url) => (url === "/api/facts/status" ? { body: [] } : undefined));
    renderWithProviders(<FactReview facts={[fact("a", "candidate"), fact("b", "candidate"), fact("c", "confirmed")]} />);
    expect(screen.getByText(/never used in matching or generated documents/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /confirm all 2/i }));
    await waitFor(() => expect(calls.some((c) => c.url === "/api/facts/status")).toBe(true));
    const body = JSON.parse(calls.find((c) => c.url === "/api/facts/status")!.init.body as string);
    expect(body).toEqual({ fact_ids: ["a", "b"], status: "confirmed" });
  });

  it("exposes accessible per-fact actions", () => {
    mockFetch(() => undefined);
    renderWithProviders(<FactReview facts={[fact("a", "candidate", "Built X")]} />);
    expect(screen.getByRole("button", { name: "Confirm: Built X" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject: Built X" })).toBeInTheDocument();
  });
});

describe("ScoreBreakdown", () => {
  const detail: MatchDetail = {
    breakdown: {
      components: {
        skills: { value: 0.9, status: "known", weight: 0.4, contribution: 36, detail: "8/8 required" },
        semantic: { value: null, status: "unknown", weight: 0.1, contribution: 4, detail: "No embedding" },
      },
      filters: [{ name: "location", passed: false, reason: "Location outside your preferences" }],
    },
    explanation: {
      fit_reasons: ["Strong Python"],
      matched_skills: ["Python"],
      missing_or_uncertain: ["Kubernetes"],
      projects_to_highlight: [],
      questions_to_investigate: ["Salary?"],
      recommended_action: "research_first",
    },
    config_snapshot: { version: "match-config@1" },
    highlight_facts: [],
    scored_at: "2026-01-01T00:00:00Z",
  };

  it("shows score, confidence, unknown components and failed filters", () => {
    renderWithProviders(
      <ScoreBreakdown match={{ score: 24.6, confidence: 0.7, eligible: false, recommended_action: "research_first" }} detail={detail} />,
    );
    expect(screen.getByText("25")).toBeInTheDocument();
    expect(screen.getByText("70%")).toBeInTheDocument();
    expect(screen.getByText("unknown")).toBeInTheDocument();
    expect(screen.getByText(/hard filter failed/i)).toBeInTheDocument();
    expect(screen.getByLabelText("failed")).toBeInTheDocument();
    expect(screen.getByText("Research first")).toBeInTheDocument();
    expect(screen.getAllByRole("progressbar")).toHaveLength(2);
  });
});

describe("ScamPanel", () => {
  it("uses probabilistic language and lets the user report a false positive", async () => {
    const calls = mockFetch((url) => (url.endsWith("/scam-feedback") ? { status: 201, body: { ok: true } } : undefined));
    const report: ScamReport = {
      level: "high",
      confidence: 0.8,
      summary: "This posting shows signals commonly associated with recruitment scams.",
      signals: [{ code: "upfront_fee", severity: "high", message: "Asks for a fee", evidence: "pay a registration fee" }],
    };
    renderWithProviders(<ScamPanel report={report} jobId="j1" />);
    expect(screen.getByText(/never mean a company is fraudulent/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /report false positive/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Reported" })).toBeDisabled());
    expect(calls.some((c) => c.url === "/api/jobs/j1/scam-feedback")).toBe(true);
  });
});
