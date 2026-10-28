import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  Bell,
  Briefcase,
  FileText,
  GraduationCap,
  Inbox,
  KanbanSquare,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  Plug,
  Settings as SettingsIcon,
  Sun,
  UserRound,
  WifiOff,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { api } from "@/api/client";
import type { Dashboard } from "@/api/types";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { cn } from "./ui";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/jobs", label: "Jobs", icon: Briefcase },
  { to: "/tracker", label: "Tracker", icon: KanbanSquare },
  { to: "/documents", label: "Resume Studio", icon: FileText },
  { to: "/inbox", label: "Inbox", icon: Inbox, badge: "pending_triage" as const },
  { to: "/interview-prep", label: "Interview Prep", icon: GraduationCap },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/profile", label: "Profile & Facts", icon: UserRound },
  { to: "/integrations", label: "Sources & Integrations", icon: Plug },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

function useOnline(): boolean {
  const [online, setOnline] = useState(typeof navigator === "undefined" ? true : navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return online;
}

export function Layout() {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const online = useOnline();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<Dashboard>("/api/dashboard"), staleTime: 30_000 });
  useEffect(() => setOpen(false), [location.pathname]);

  const counts = dash.data?.counts;
  return (
    <div className="flex min-h-full">
      <a href="#main" className="sr-only-focusable fixed left-2 top-2 z-[70] rounded bg-primary px-3 py-2 text-primary-fg">
        Skip to content
      </a>
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 w-64 shrink-0 border-r border-border bg-surface p-4 transition-transform lg:static lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
        aria-label="Main navigation"
      >
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-2 font-semibold">
            <img src="/favicon.svg" alt="" className="h-7 w-7" />
            JobPilot AI
          </div>
          <button className="lg:hidden" aria-label="Close menu" onClick={() => setOpen(false)}>
            <X className="h-5 w-5" aria-hidden />
          </button>
        </div>
        <nav>
          <ul className="space-y-1">
            {NAV.map((n) => {
              const badge = n.badge && counts ? counts[n.badge] : 0;
              return (
                <li key={n.to}>
                  <NavLink
                    to={n.to}
                    end={n.end}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-3 rounded px-3 py-2 text-sm",
                        isActive ? "bg-primary/10 font-medium text-primary" : "text-subtle hover:bg-muted hover:text-fg",
                      )
                    }
                  >
                    <n.icon className="h-4 w-4" aria-hidden />
                    <span className="flex-1">{n.label}</span>
                    {badge > 0 && (
                      <span className="rounded-full bg-primary px-2 text-xs text-primary-fg" aria-label={`${badge} pending`}>
                        {badge}
                      </span>
                    )}
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </nav>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/40 lg:hidden" onClick={() => setOpen(false)} aria-hidden />}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border bg-surface/90 px-4 backdrop-blur">
          <button className="lg:hidden" aria-label="Open menu" onClick={() => setOpen(true)}>
            <Menu className="h-5 w-5" aria-hidden />
          </button>
          <div className="flex-1" />
          <NavLink to="/notifications" className="relative rounded p-2 hover:bg-muted" aria-label={`Notifications${counts?.unread_notifications ? `, ${counts.unread_notifications} unread` : ""}`}>
            <Bell className="h-5 w-5" aria-hidden />
            {!!counts?.unread_notifications && <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-danger" aria-hidden />}
          </NavLink>
          <button onClick={toggle} className="rounded p-2 hover:bg-muted" aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
            {theme === "dark" ? <Sun className="h-5 w-5" aria-hidden /> : <Moon className="h-5 w-5" aria-hidden />}
          </button>
          <span className="hidden text-sm text-subtle sm:inline">{user?.email}</span>
          <button onClick={() => void logout()} className="rounded p-2 hover:bg-muted" aria-label="Sign out">
            <LogOut className="h-5 w-5" aria-hidden />
          </button>
        </header>
        {!online && (
          <div role="status" className="flex items-center gap-2 bg-warning/15 px-4 py-2 text-sm text-warning">
            <WifiOff className="h-4 w-4" aria-hidden /> You're offline. Changes can't be saved until you reconnect.
          </div>
        )}
        <main id="main" className="mx-auto w-full max-w-7xl flex-1 p-4 sm:p-6" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
