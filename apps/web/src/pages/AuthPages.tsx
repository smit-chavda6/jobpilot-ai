import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router";
import { z } from "zod";
import { api, ApiError, errorMessage } from "@/api/client";
import { Button, Card, Field, Input } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { credentialsSchema, registerSchema, resetSchema } from "@/lib/schemas";

type Mode = "login" | "register" | "forgot" | "reset" | "verify";

function Shell({ title, children, footer }: { title: string; children: ReactNode; footer?: ReactNode }) {
  return (
    <main className="flex min-h-full items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2 text-lg font-semibold">
          <img src="/favicon.svg" alt="" className="h-8 w-8" /> JobPilot AI
        </div>
        <Card className="p-6">
          <h1 className="mb-4 text-xl font-semibold">{title}</h1>
          {children}
        </Card>
        {footer && <div className="mt-4 text-center text-sm text-subtle">{footer}</div>}
      </div>
    </main>
  );
}

function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded border border-danger/40 bg-danger/5 p-2 text-sm text-danger">
      {message}
    </p>
  );
}

function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<z.infer<typeof credentialsSchema>>({ resolver: zodResolver(credentialsSchema) });
  const onSubmit = form.handleSubmit(async (v) => {
    setError(null);
    try {
      await login(v.email, v.password);
      navigate((location.state as { from?: string } | null)?.from ?? "/", { replace: true });
    } catch (e) {
      setError(errorMessage(e));
    }
  });
  const errs = form.formState.errors;
  return (
    <Shell
      title="Sign in"
      footer={
        <>
          New here? <Link className="text-primary hover:underline" to="/register">Create an account</Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <FormError message={error} />
        <Field label="Email" error={errs.email?.message}>
          {(id, d) => <Input id={id} type="email" autoComplete="email" aria-describedby={d} aria-invalid={!!errs.email} {...form.register("email")} />}
        </Field>
        <Field label="Password" error={errs.password?.message}>
          {(id, d) => (
            <Input id={id} type="password" autoComplete="current-password" aria-describedby={d} aria-invalid={!!errs.password} {...form.register("password")} />
          )}
        </Field>
        <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
          Sign in
        </Button>
        <Link to="/forgot-password" className="block text-center text-sm text-primary hover:underline">
          Forgot password?
        </Link>
      </form>
    </Shell>
  );
}

function Register() {
  const { register: signUp } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<z.infer<typeof registerSchema>>({ resolver: zodResolver(registerSchema) });
  const onSubmit = form.handleSubmit(async (v) => {
    setError(null);
    try {
      await signUp(v.email, v.password);
      navigate("/onboarding", { replace: true });
    } catch (e) {
      setError(errorMessage(e));
    }
  });
  const errs = form.formState.errors;
  return (
    <Shell
      title="Create your account"
      footer={
        <>
          Already have an account? <Link className="text-primary hover:underline" to="/login">Sign in</Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <FormError message={error} />
        <Field label="Email" error={errs.email?.message}>
          {(id, d) => <Input id={id} type="email" autoComplete="email" aria-describedby={d} aria-invalid={!!errs.email} {...form.register("email")} />}
        </Field>
        <Field label="Password" hint="At least 10 characters, with an uppercase letter and a digit." error={errs.password?.message}>
          {(id, d) => <Input id={id} type="password" autoComplete="new-password" aria-describedby={d} aria-invalid={!!errs.password} {...form.register("password")} />}
        </Field>
        <Field label="Confirm password" error={errs.confirm?.message}>
          {(id, d) => <Input id={id} type="password" autoComplete="new-password" aria-describedby={d} aria-invalid={!!errs.confirm} {...form.register("confirm")} />}
        </Field>
        <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
          Create account
        </Button>
        <p className="text-xs text-subtle">
          JobPilot never applies, emails or submits anything on your behalf without your explicit approval.
        </p>
      </form>
    </Shell>
  );
}

/** In development the API keeps transactional emails in a dev mailbox instead of sending them. */
function DevMailbox({ email }: { email: string }) {
  const mail = useQuery({
    queryKey: ["dev-mailbox", email],
    queryFn: () => api.get<{ subject: string; body: string; created_at: string }[]>("/api/auth/dev-mailbox", { email }),
    enabled: !!email,
    retry: false,
  });
  if (!mail.data?.length) return null;
  return (
    <div className="mt-4 rounded border border-info/40 bg-info/5 p-3 text-sm">
      <p className="mb-1 font-medium">Development mailbox</p>
      <p className="mb-2 text-xs text-subtle">No email is sent in development. The latest message would have said:</p>
      <p className="whitespace-pre-wrap break-all font-mono text-xs">{mail.data[0]?.body}</p>
    </div>
  );
}

function Forgot() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => api.post<{ message: string }>("/api/auth/forgot-password", { email }),
    onSuccess: (r) => setSent(r.message),
  });
  return (
    <Shell title="Reset your password" footer={<Link className="text-primary hover:underline" to="/login">Back to sign in</Link>}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          m.mutate();
        }}
      >
        <FormError message={m.error ? errorMessage(m.error) : null} />
        {sent ? (
          <p role="status" className="text-sm">
            {sent}
          </p>
        ) : (
          <>
            <Field label="Email">
              {(id) => <Input id={id} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />}
            </Field>
            <Button type="submit" className="w-full" loading={m.isPending}>
              Send reset link
            </Button>
          </>
        )}
      </form>
      {sent && <DevMailbox email={email} />}
    </Shell>
  );
}

function Reset() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<z.infer<typeof resetSchema>>({ resolver: zodResolver(resetSchema) });
  const onSubmit = form.handleSubmit(async (v) => {
    setError(null);
    try {
      await api.post("/api/auth/reset-password", { token, password: v.password });
      navigate("/login", { replace: true });
    } catch (e) {
      setError(errorMessage(e));
    }
  });
  const errs = form.formState.errors;
  if (!token) return <Navigate to="/forgot-password" replace />;
  return (
    <Shell title="Choose a new password">
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <FormError message={error} />
        <Field label="New password" error={errs.password?.message}>
          {(id, d) => <Input id={id} type="password" autoComplete="new-password" aria-describedby={d} {...form.register("password")} />}
        </Field>
        <Field label="Confirm password" error={errs.confirm?.message}>
          {(id, d) => <Input id={id} type="password" autoComplete="new-password" aria-describedby={d} {...form.register("confirm")} />}
        </Field>
        <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>
          Set password
        </Button>
      </form>
    </Shell>
  );
}

function Verify() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const { user, setUser } = useAuth();
  const m = useMutation({
    mutationFn: () => api.post("/api/auth/verify-email", { token }),
    onSuccess: () => user && setUser({ ...user, email_verified: true }),
  });
  const { mutate } = m;
  useEffect(() => {
    if (token) mutate();
  }, [token, mutate]);
  return (
    <Shell title="Verify email" footer={<Link className="text-primary hover:underline" to="/">Go to JobPilot</Link>}>
      {!token && <p className="text-sm">This link is missing its token.</p>}
      {m.isPending && <p className="text-sm">Verifying…</p>}
      {m.isSuccess && <p role="status" className="text-sm text-success">Your email address is verified.</p>}
      {m.isError && (
        <p role="alert" className="text-sm text-danger">
          {m.error instanceof ApiError ? m.error.message : "This link is invalid or has expired."}
        </p>
      )}
    </Shell>
  );
}

export default function AuthPages({ mode }: { mode: Mode }) {
  const { user, loading } = useAuth();
  if ((mode === "login" || mode === "register") && !loading && user) return <Navigate to="/" replace />;
  switch (mode) {
    case "login":
      return <Login />;
    case "register":
      return <Register />;
    case "forgot":
      return <Forgot />;
    case "reset":
      return <Reset />;
    case "verify":
      return <Verify />;
  }
}

export { DevMailbox };
