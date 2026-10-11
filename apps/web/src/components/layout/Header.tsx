import { useState, useEffect } from "react";
import { Sun, Moon, Zap, User, LogOut } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import { Button } from "../ui/button";

export function Header() {
  const { user, logout } = useAuth();
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, [isDark]);

  return (
    <header className="h-16 border-b border-slate-200/80 bg-white/80 dark:border-slate-800 dark:bg-slate-900/80 backdrop-blur-md px-6 flex items-center justify-between sticky top-0 z-30">
      <div className="flex items-center gap-4">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
          Candidate Workspace
        </h2>
      </div>

      <div className="flex items-center gap-4">
        {/* Token Budget Meter */}
        <div className="hidden md:flex items-center gap-2.5 px-3 py-1.5 rounded-full bg-slate-100 dark:bg-slate-800 text-xs border border-slate-200/60 dark:border-slate-700">
          <Zap className="w-3.5 h-3.5 text-amber-500 fill-amber-500" />
          <span className="text-slate-600 dark:text-slate-300 font-medium">Daily AI Budget:</span>
          <span className="font-bold text-slate-900 dark:text-slate-100">12,450 / 50,000</span>
          <div className="w-16 h-1.5 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden ml-1">
            <div className="h-full bg-indigo-500 rounded-full" style={{ width: "25%" }} />
          </div>
        </div>

        {/* Theme Toggle */}
        <button
          onClick={() => setIsDark(!isDark)}
          className="p-2 rounded-lg text-slate-500 hover:text-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 dark:text-slate-400 transition-colors"
          aria-label="Toggle color theme"
        >
          {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>

        {/* User Identity & Logout */}
        {user ? (
          <div className="flex items-center gap-3 pl-2 border-l border-slate-200 dark:border-slate-800">
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 rounded-full bg-indigo-100 dark:bg-indigo-900/50 flex items-center justify-center text-indigo-700 dark:text-indigo-300 font-bold text-xs">
                {user.email.substring(0, 2).toUpperCase()}
              </div>
              <span className="text-xs font-semibold text-slate-800 dark:text-slate-200 hidden sm:inline">
                {user.email}
              </span>
            </div>
            <button
              onClick={logout}
              className="p-1.5 text-slate-400 hover:text-rose-600 rounded-lg hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-colors"
              title="Log out"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        ) : (
          <Button size="sm" variant="outline" className="text-xs">
            <User className="w-3.5 h-3.5 mr-1.5" /> Log in
          </Button>
        )}
      </div>
    </header>
  );
}
