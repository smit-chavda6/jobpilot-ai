/**
 * Fetch wrapper for the JobPilot API.
 * - Session lives in HttpOnly cookies; the SPA never sees tokens.
 * - CSRF double-submit: token from GET /api/auth/csrf is echoed in X-CSRF-Token on writes.
 * - On 401 the access token is refreshed once (rotating refresh cookie) and the call retried.
 * - Errors are normalised to ApiError using the server envelope {error:{code,message,details,request_id}}.
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: unknown = null,
    public requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);
let csrfToken: string | null = null;
let refreshing: Promise<boolean> | null = null;

async function ensureCsrf(force = false): Promise<string> {
  if (csrfToken && !force) return csrfToken;
  const r = await fetch("/api/auth/csrf", { credentials: "same-origin" });
  const body = (await r.json()) as { csrf_token: string };
  csrfToken = body.csrf_token;
  return csrfToken;
}

async function tryRefresh(): Promise<boolean> {
  refreshing ??= (async () => {
    try {
      const token = await ensureCsrf();
      const r = await fetch("/api/auth/refresh", {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRF-Token": token },
      });
      return r.ok;
    } catch {
      return false;
    } finally {
      setTimeout(() => (refreshing = null), 0);
    }
  })();
  return refreshing;
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  form?: FormData;
  headers?: Record<string, string>;
  idempotencyKey?: string;
  signal?: AbortSignal;
  raw?: boolean;
}

const NO_REFRESH = ["/api/auth/login", "/api/auth/register", "/api/auth/refresh", "/api/auth/csrf"];

async function toError(r: Response): Promise<ApiError> {
  try {
    const body = (await r.json()) as { error?: { code: string; message: string; details: unknown; request_id: string } };
    if (body.error) return new ApiError(r.status, body.error.code, body.error.message, body.error.details, body.error.request_id);
  } catch {
    /* non-JSON body */
  }
  return new ApiError(r.status, "http_error", r.statusText || `Request failed (${r.status})`);
}

export async function request<T>(path: string, opts: RequestOptions = {}, retry = true): Promise<T> {
  const method = opts.method ?? (opts.body !== undefined || opts.form ? "POST" : "GET");
  const headers: Record<string, string> = { Accept: "application/json", ...opts.headers };
  if (UNSAFE.has(method)) headers["X-CSRF-Token"] = await ensureCsrf();
  if (opts.idempotencyKey) headers["Idempotency-Key"] = opts.idempotencyKey;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }

  let r: Response;
  try {
    r = await fetch(path, { method, headers, body, credentials: "same-origin", signal: opts.signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "network_error", "Can't reach the server. Check your connection and try again.");
  }

  if (retry && r.status === 401 && !NO_REFRESH.includes(path) && (await tryRefresh())) {
    return request<T>(path, opts, false);
  }
  if (retry && r.status === 403 && UNSAFE.has(method)) {
    const err = await toError(r.clone());
    if (err.code === "csrf_failed") {
      await ensureCsrf(true);
      return request<T>(path, opts, false);
    }
  }
  if (!r.ok) throw await toError(r);
  if (opts.raw) return r as unknown as T;
  if (r.status === 204) return undefined as T;
  const ct = r.headers.get("content-type") ?? "";
  return (ct.includes("application/json") ? await r.json() : await r.text()) as T;
}

export const api = {
  get: <T>(path: string, params?: Record<string, string | number | boolean | undefined | null>) => {
    const qs = params
      ? new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== null && v !== "")
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : "";
    return request<T>(qs ? `${path}?${qs}` : path);
  },
  post: <T>(path: string, body?: unknown, opts: Omit<RequestOptions, "body" | "method"> = {}) =>
    request<T>(path, { ...opts, method: "POST", body: body ?? {} }),
  put: <T>(path: string, body: unknown, opts: Omit<RequestOptions, "body" | "method"> = {}) =>
    request<T>(path, { ...opts, method: "PUT", body }),
  patch: <T>(path: string, body: unknown, opts: Omit<RequestOptions, "body" | "method"> = {}) =>
    request<T>(path, { ...opts, method: "PATCH", body }),
  del: <T = void>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, file: File, opts: Omit<RequestOptions, "form" | "method"> = {}) => {
    const form = new FormData();
    form.append("file", file);
    return request<T>(path, { ...opts, method: "POST", form });
  },
  download: async (path: string, filename: string, method = "GET") => {
    const r = await request<Response>(path, { method, raw: true });
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};

export function newIdempotencyKey(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "Something went wrong";
}
