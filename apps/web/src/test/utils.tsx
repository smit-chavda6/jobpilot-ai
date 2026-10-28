import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { ToastProvider } from "@/components/Toast";

export function renderWithProviders(ui: ReactElement, route = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return {
    qc,
    ...render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[route]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <ToastProvider>{ui}</ToastProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  };
}

type Handler = (url: string, init: RequestInit) => { status?: number; body?: unknown } | undefined;

/** Installs a fetch mock. CSRF is always served; other calls go to `handler`. Returns the call log. */
export function mockFetch(handler: Handler) {
  const calls: { url: string; init: RequestInit }[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = typeof input === "string" ? input : input.toString();
    calls.push({ url, init });
    if (url === "/api/auth/csrf") return json(200, { csrf_token: "tok-123" });
    const r = handler(url, init) ?? { status: 404, body: { error: { code: "not_found", message: "Not found", details: null, request_id: "r" } } };
    return json(r.status ?? 200, r.body ?? {});
  });
  vi.stubGlobal("fetch", fn);
  return calls;
}

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}
