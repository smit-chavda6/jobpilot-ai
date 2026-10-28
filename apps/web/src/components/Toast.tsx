import { CheckCircle2, Info, X, XCircle } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { cn } from "./ui";

type Kind = "success" | "error" | "info";
interface Toast {
  id: number;
  kind: Kind;
  message: string;
  action?: { label: string; onClick: () => void };
}

interface ToastApi {
  show: (message: string, kind?: Kind, action?: Toast["action"]) => void;
  success: (message: string, action?: Toast["action"]) => void;
  error: (message: string) => void;
}

const Ctx = createContext<ToastApi | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);
  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const show = useCallback(
    (message: string, kind: Kind = "info", action?: Toast["action"]) => {
      const id = ++seq.current;
      setToasts((t) => [...t.slice(-3), { id, kind, message, action }]);
      setTimeout(() => dismiss(id), action ? 10000 : 5000);
    },
    [dismiss],
  );
  const value = useMemo<ToastApi>(
    () => ({ show, success: (m, a) => show(m, "success", a), error: (m) => show(m, "error") }),
    [show],
  );
  return (
    <Ctx.Provider value={value}>
      {children}
      <div aria-live="polite" aria-atomic="false" className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-80 flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.kind === "error" ? "alert" : "status"}
            className={cn(
              "pointer-events-auto flex items-start gap-2 rounded-lg border bg-surface p-3 text-sm shadow-lg",
              t.kind === "error" ? "border-danger/40" : "border-border",
            )}
          >
            {t.kind === "success" ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden />
            ) : t.kind === "error" ? (
              <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger" aria-hidden />
            ) : (
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-info" aria-hidden />
            )}
            <p className="flex-1">{t.message}</p>
            {t.action && (
              <button
                className="font-semibold text-primary hover:underline"
                onClick={() => {
                  t.action?.onClick();
                  dismiss(t.id);
                }}
              >
                {t.action.label}
              </button>
            )}
            <button aria-label="Dismiss notification" onClick={() => dismiss(t.id)} className="text-subtle hover:text-fg">
              <X className="h-4 w-4" aria-hidden />
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}
