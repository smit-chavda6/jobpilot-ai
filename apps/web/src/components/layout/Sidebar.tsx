import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Briefcase,
  FileCheck2,
  KanbanSquare,
  Sparkles,
  BarChart3,
  Sliders,
  Settings,
  Component,
} from "lucide-react";
import { cn } from "../../lib/utils";

const navigationItems = [
  { name: "Dashboard", href: "/", icon: LayoutDashboard },
  { name: "Jobs & Discovery", href: "/jobs", icon: Briefcase },
  { name: "Resume Studio", href: "/resumes", icon: FileCheck2 },
  { name: "Application Tracker", href: "/tracker", icon: KanbanSquare },
  { name: "Interview Prep", href: "/interviews", icon: Sparkles },
  { name: "Analytics", href: "/analytics", icon: BarChart3 },
  { name: "Integrations", href: "/integrations", icon: Sliders },
  { name: "Settings", href: "/settings", icon: Settings },
  { name: "Component Gallery", href: "/gallery", icon: Component },
];

export function Sidebar() {
  return (
    <aside className="w-64 border-r border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-900/90 flex flex-col h-screen sticky top-0 shrink-0">
      <div className="h-16 flex items-center px-6 border-b border-slate-100 dark:border-slate-800/80 gap-3">
        <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white shadow-md shadow-indigo-500/25">
          <Sparkles className="w-5 h-5" />
        </div>
        <div>
          <span className="font-extrabold text-base tracking-tight bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent dark:from-indigo-400 dark:to-violet-400">
            JobPilot AI
          </span>
          <span className="block text-[10px] uppercase font-bold text-slate-400 tracking-wider">
            Verified Copilot
          </span>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navigationItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.name}
              to={item.href}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all group",
                  isActive
                    ? "bg-indigo-50 text-indigo-700 font-semibold dark:bg-indigo-950/50 dark:text-indigo-300"
                    : "text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200"
                )
              }
            >
              <Icon className="w-4 h-4 shrink-0 transition-transform group-hover:scale-110" />
              <span>{item.name}</span>
            </NavLink>
          );
        })}
      </nav>

      {/* Safety & Compliance Badge */}
      <div className="p-4 m-3 rounded-xl bg-slate-50 border border-slate-200/60 dark:bg-slate-800/40 dark:border-slate-800 text-xs text-slate-500 dark:text-slate-400">
        <p className="font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-emerald-500"></span>
          Human in the Loop
        </p>
        <p className="mt-1 text-[11px] leading-relaxed">
          Zero unapproved actions. Every application submission strictly user-confirmed.
        </p>
      </div>
    </aside>
  );
}
