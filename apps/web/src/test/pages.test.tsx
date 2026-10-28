import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Analytics as AnalyticsData, ApplicationsPage } from "@/api/types";
import Analytics from "@/pages/Analytics";
import Tracker from "@/pages/Tracker";
import { mockFetch, renderWithProviders } from "./utils";

afterEach(() => vi.unstubAllGlobals());

const rate = (n: number, s: number) => ({
  n,
  successes: s,
  rate: n ? s / n : null,
  ci_low: n >= 20 ? 0.1 : null,
  ci_high: n >= 20 ? 0.5 : null,
  insufficient_data: n < 20,
  min_n: 20,
});

describe("Analytics", () => {
  it("shows insufficient data below the threshold and Wilson CI above it", async () => {
    const data: AnalyticsData = {
      totals: { jobs: 30, applications: 25, submitted: 22, demo_applications: 0, include_demo: false },
      by_status: { submitted_confirmed: 22 },
      response_rate: rate(22, 6),
      interview_rate: rate(5, 1),
      offer_rate: rate(0, 0),
      funnel: [],
      time_to_response: { n: 0, median_days: null, buckets: [] },
      by_source: [],
      score_band_vs_interview: [],
      weekly_submissions: [],
      min_n: 20,
      note: "Correlations are not causal.",
    };
    mockFetch((url) => (url.startsWith("/api/analytics") ? { body: data } : undefined));
    renderWithProviders(<Analytics />);
    expect(await screen.findByText("27.3%")).toBeInTheDocument();
    expect(screen.getByText(/6\/22 · 95% CI 10%–50%/)).toBeInTheDocument();
    expect(screen.getAllByText("Insufficient data")).toHaveLength(2);
    expect(screen.getByText("Correlations are not causal.")).toBeInTheDocument();
  });
});

describe("Tracker", () => {
  const page: ApplicationsPage = {
    items: [
      {
        id: "a1",
        job_id: "j1",
        status: "submitted_confirmed",
        resume_doc_id: null,
        cover_letter_doc_id: null,
        adapter_level: "manual_handoff",
        notes: "",
        submitted_at: "2026-01-02T00:00:00Z",
        last_status_at: "2026-01-02T00:00:00Z",
        created_at: "2026-01-01T00:00:00Z",
        version: 4,
        is_demo: true,
        allowed_moves: ["interviewing", "rejected"],
        job: { id: "j1", title: "ML Engineer", company: "Nimbus", url: null, location: "", source: "manual_paste" },
      },
    ],
    next_cursor: null,
    columns: { Applied: ["submitted_confirmed", "ghosted"], Interviewing: ["interviewing"] },
  };

  it("offers a keyboard-accessible move menu with only allowed targets, sends If-Match and offers undo", async () => {
    const calls = mockFetch((url) => {
      if (url.startsWith("/api/applications?")) return { body: page };
      if (url === "/api/applications/a1/move") return { body: { ...page.items[0], status: "interviewing" } };
      return undefined;
    });
    renderWithProviders(<Tracker />);
    const applied = await screen.findByRole("region", { name: /Applied column, 1 applications/ });
    expect(within(applied).getByText(/demo/i)).toBeInTheDocument();
    const menu = within(applied).getByRole("combobox", { name: "Move ML Engineer to" });
    const options = within(menu)
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(options).toEqual(["Move to…", "Interviewing", "Rejected"]);
    await userEvent.selectOptions(menu, "interviewing");
    await waitFor(() => expect(calls.some((c) => c.url === "/api/applications/a1/move")).toBe(true));
    const move = calls.find((c) => c.url === "/api/applications/a1/move")!;
    expect((move.init.headers as Record<string, string>)["If-Match"]).toBe('W/"4"');
    expect(await screen.findByRole("button", { name: "Undo" })).toBeInTheDocument();
  });
});
