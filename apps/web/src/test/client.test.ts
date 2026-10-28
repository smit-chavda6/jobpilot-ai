import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/api/client";
import { mockFetch } from "./utils";

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("sends the CSRF token and Idempotency-Key on writes", async () => {
    const calls = mockFetch((url) => (url === "/api/jobs/import/manual_paste" ? { status: 201, body: { ok: true } } : undefined));
    await api.post("/api/jobs/import/manual_paste", { text: "x" }, { idempotencyKey: "k1" });
    const write = calls.find((c) => c.url === "/api/jobs/import/manual_paste")!;
    const headers = write.init.headers as Record<string, string>;
    expect(headers["X-CSRF-Token"]).toBe("tok-123");
    expect(headers["Idempotency-Key"]).toBe("k1");
    expect(write.init.credentials).toBe("same-origin");
  });

  it("does not send CSRF on reads and drops empty params", async () => {
    const calls = mockFetch(() => ({ body: [] }));
    await api.get("/api/facts", { status: "confirmed", empty: "" });
    expect(calls[0]!.url).toBe("/api/facts?status=confirmed");
    expect((calls[0]!.init.headers as Record<string, string>)["X-CSRF-Token"]).toBeUndefined();
  });

  it("parses the error envelope into ApiError", async () => {
    mockFetch(() => ({
      status: 409,
      body: { error: { code: "duplicate_application", message: "Already applied", details: { a: 1 }, request_id: "rid" } },
    }));
    const err = await api.post("/api/applications", { job_id: "x" }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 409, code: "duplicate_application", message: "Already applied", requestId: "rid" });
  });

  it("refreshes the session once on 401 and retries", async () => {
    let first = true;
    const calls = mockFetch((url) => {
      if (url === "/api/profile") {
        if (first) {
          first = false;
          return { status: 401, body: { error: { code: "unauthorized", message: "Authentication required", details: null, request_id: "r" } } };
        }
        return { body: { full_name: "A" } };
      }
      if (url === "/api/auth/refresh") return { body: { ok: true } };
      return undefined;
    });
    await expect(api.get("/api/profile")).resolves.toEqual({ full_name: "A" });
    // The CSRF token is cached module-wide, so only the three real calls are asserted (in order).
    expect(calls.map((c) => c.url).filter((u) => u !== "/api/auth/csrf")).toEqual(["/api/profile", "/api/auth/refresh", "/api/profile"]);
    expect(calls.filter((c) => c.url === "/api/auth/refresh")).toHaveLength(1);
    expect(calls.filter((c) => c.url === "/api/profile")).toHaveLength(2);
  });
});
