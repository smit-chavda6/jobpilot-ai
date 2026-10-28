import { clsx } from "clsx";
import { AlertTriangle, Inbox, Loader2, RefreshCw, WifiOff } from "lucide-react";
import {
  forwardRef,
  useEffect,
  useId,
  useRef,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { errorMessage } from "@/api/client";

export const cn = clsx;

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-primary text-primary-fg hover:bg-primary/90",
  secondary: "border border-border bg-surface text-fg hover:bg-muted",
  ghost: "text-fg hover:bg-muted",
  danger: "bg-danger text-white hover:bg-danger/90 dark:text-bg",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading, icon, className, children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "h-8 px-3 text-sm" : "h-10 px-4 text-sm",
        VARIANTS[variant],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
});

export function Card({ className, children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("rounded-lg border border-border bg-surface p-4 shadow-sm", className)} {...rest}>
      {children}
    </div>
  );
}

export function CardTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-2">
      <h2 className="text-base font-semibold">{children}</h2>
      {action}
    </div>
  );
}

type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "primary";
const TONES: Record<Tone, string> = {
  neutral: "bg-muted text-subtle",
  success: "bg-success/10 text-success",
  warning: "bg-warning/10 text-warning",
  danger: "bg-danger/10 text-danger",
  info: "bg-info/10 text-info",
  primary: "bg-primary/10 text-primary",
};

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-xs font-medium", TONES[tone], className)}>
      {children}
    </span>
  );
}

export function DemoBadge() {
  return (
    <Badge tone="warning" className="uppercase tracking-wide">
      Demo
    </Badge>
  );
}

const fieldBase =
  "w-full rounded border border-border bg-surface px-3 text-sm text-fg placeholder:text-subtle/70 focus:border-primary disabled:opacity-60";

interface FieldProps {
  label: string;
  hint?: string;
  error?: string;
  children: (id: string, describedBy: string | undefined) => ReactNode;
  className?: string;
}

export function Field({ label, hint, error, children, className }: FieldProps) {
  const id = useId();
  const describedBy = [hint ? `${id}-hint` : null, error ? `${id}-err` : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cn("space-y-1", className)}>
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      {children(id, describedBy)}
      {hint && (
        <p id={`${id}-hint`} className="text-xs text-subtle">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-err`} role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...rest },
  ref,
) {
  return <input ref={ref} className={cn(fieldBase, "h-10", className)} {...rest} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea(
  { className, ...rest },
  ref,
) {
  return <textarea ref={ref} className={cn(fieldBase, "min-h-[6rem] py-2", className)} {...rest} />;
});

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...rest },
  ref,
) {
  return (
    <select ref={ref} className={cn(fieldBase, "h-10", className)} {...rest}>
      {children}
    </select>
  );
});

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 p-8 text-subtle">
      <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
      <span className="text-sm">{label}…</span>
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border p-8 text-center">
      <Inbox className="h-8 w-8 text-subtle" aria-hidden />
      <p className="font-medium">{title}</p>
      {children && <div className="max-w-md text-sm text-subtle">{children}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const offline = typeof navigator !== "undefined" && !navigator.onLine;
  return (
    <div role="alert" className="flex flex-col items-center gap-2 rounded-lg border border-danger/30 bg-danger/5 p-6 text-center">
      {offline ? <WifiOff className="h-6 w-6 text-danger" aria-hidden /> : <AlertTriangle className="h-6 w-6 text-danger" aria-hidden />}
      <p className="font-medium">{offline ? "You're offline" : "Couldn't load this"}</p>
      <p className="text-sm text-subtle">{offline ? "Reconnect to see the latest data." : errorMessage(error)}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry} icon={<RefreshCw className="h-4 w-4" aria-hidden />}>
          Try again
        </Button>
      )}
    </div>
  );
}

/** Renders loading / error / empty / data states for a TanStack query consistently. */
export function QueryView<T>({
  query,
  empty,
  isEmpty,
  children,
  loadingLabel,
}: {
  query: { data: T | undefined; isLoading: boolean; error: unknown; refetch: () => unknown };
  empty?: ReactNode;
  isEmpty?: (d: T) => boolean;
  children: (d: T) => ReactNode;
  loadingLabel?: string;
}) {
  if (query.isLoading) return <Spinner label={loadingLabel} />;
  if (query.error) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  if (query.data === undefined) return null;
  if (empty && isEmpty?.(query.data)) return <>{empty}</>;
  return <>{children(query.data)}</>;
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-subtle">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Modal({
  open,
  title,
  onClose,
  children,
  footer,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const el = ref.current;
    const focusable = () =>
      Array.from(el?.querySelectorAll<HTMLElement>("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])") ?? []).filter(
        (n) => !n.hasAttribute("disabled"),
      );
    focusable()[0]?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") {
        const f = focusable();
        if (f.length === 0) return;
        const first = f[0]!;
        const last = f[f.length - 1]!;
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      prev?.focus();
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onMouseDown={onClose}>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-lg rounded-lg border border-border bg-surface p-5 shadow-xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2 id={titleId} className="mb-3 text-lg font-semibold">
          {title}
        </h2>
        <div className="space-y-3 text-sm">{children}</div>
        {footer && <div className="mt-5 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
}

export function ProgressBar({ value, label, tone = "primary" }: { value: number; label: string; tone?: "primary" | "success" | "warning" | "danger" }) {
  const pct = Math.max(0, Math.min(100, value));
  const color = { primary: "bg-primary", success: "bg-success", warning: "bg-warning", danger: "bg-danger" }[tone];
  return (
    <div role="progressbar" aria-label={label} aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} className="h-2 w-full overflow-hidden rounded-full bg-muted">
      <div className={cn("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Checkbox({ label, ...rest }: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2 text-sm">
      <input type="checkbox" className="h-4 w-4 rounded border-border accent-[rgb(var(--primary))]" {...rest} />
      {label}
    </label>
  );
}
