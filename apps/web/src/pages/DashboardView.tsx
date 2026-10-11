import { Link } from "react-router-dom";
import {
  Briefcase,
  CheckCircle2,
  Clock,
  Sparkles,
  TrendingUp,
  AlertCircle,
  ArrowRight,
  ShieldAlert,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/card";

export function DashboardView() {
  const stats = [
    { label: "Discovered Jobs", value: "32", change: "+5 today", icon: Briefcase, color: "text-indigo-600" },
    { label: "Matches > 85%", value: "14", change: "High fidelity", icon: Sparkles, color: "text-violet-600" },
    { label: "Awaiting Approval", value: "3", change: "Human gate", icon: Clock, color: "text-amber-600" },
    { label: "Active Applications", value: "8", change: "Tracked live", icon: TrendingUp, color: "text-emerald-600" },
  ];

  const pendingApprovals = [
    {
      id: "app-1",
      company: "Stripe",
      role: "Staff Infrastructure Engineer",
      matchScore: 94,
      groundedClaims: 18,
      status: "awaiting_approval",
    },
    {
      id: "app-2",
      company: "Datadog",
      role: "Senior Distributed Systems Engineer",
      matchScore: 91,
      groundedClaims: 15,
      status: "awaiting_approval",
    },
  ];

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      {/* Welcome & Quick Action */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-200/60 dark:border-slate-800">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
            Welcome to JobPilot AI
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Grounded, compliance-first job hunting copilot. Every action remains under your explicit approval.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link to="/resumes">
            <Button variant="outline" size="sm">
              Verify Facts
            </Button>
          </Link>
          <Link to="/jobs">
            <Button size="sm">
              <Briefcase className="w-4 h-4 mr-1.5" /> Import Jobs
            </Button>
          </Link>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.label} className="hover:shadow-md transition-shadow">
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">{stat.label}</span>
                  <Icon className={`w-5 h-5 ${stat.color}`} />
                </div>
                <div className="mt-3 flex items-baseline gap-2">
                  <span className="text-3xl font-extrabold tracking-tight">{stat.value}</span>
                  <span className="text-xs font-medium text-slate-400">{stat.change}</span>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Core Grid: Approval Gates & High Matches */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Pending Approvals (Human-in-the-loop Gate) */}
        <Card className="lg:col-span-2 border-amber-200/60 dark:border-amber-950/60 bg-gradient-to-b from-white to-amber-50/20 dark:from-slate-900 dark:to-amber-950/10">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2 text-slate-900 dark:text-slate-100">
                  <AlertCircle className="w-5 h-5 text-amber-500" />
                  Approval Gate Checkpoints
                </CardTitle>
                <CardDescription>
                  Tailored materials ready for review. Submissions will NOT proceed without your signed confirmation.
                </CardDescription>
              </div>
              <Badge variant="warning">3 Awaiting Review</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {pendingApprovals.map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between p-4 rounded-xl border border-slate-200/70 bg-white dark:bg-slate-800/80 dark:border-slate-700/80 hover:border-indigo-300 transition-colors"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-sm text-slate-900 dark:text-slate-100">{item.role}</span>
                    <Badge variant="secondary" className="text-[11px] font-semibold">
                      {item.company}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-3 mt-1.5 text-xs text-slate-500 dark:text-slate-400">
                    <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-semibold">
                      <CheckCircle2 className="w-3.5 h-3.5" /> {item.matchScore}% Match
                    </span>
                    <span>•</span>
                    <span>{item.groundedClaims} Verified Fact Citations</span>
                  </div>
                </div>
                <Link to="/tracker">
                  <Button size="sm" variant="primary" className="text-xs">
                    Review & Approve <ArrowRight className="w-3.5 h-3.5 ml-1" />
                  </Button>
                </Link>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Operating Guardrails & Compliance Status */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-indigo-500" /> Compliance & Grounding
            </CardTitle>
            <CardDescription className="text-xs">Real-time safety checks active on all models</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-xs">
            <div className="flex items-start gap-3 p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200/50">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
              <div>
                <p className="font-semibold text-emerald-900 dark:text-emerald-200">Zero Hallucinations Policy</p>
                <p className="text-emerald-700 dark:text-emerald-400 text-[11px] mt-0.5">
                  Tailored bullets strictly validate against verified ProfileFact IDs.
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3 p-3 rounded-lg bg-indigo-50 dark:bg-indigo-950/30 border border-indigo-200/50">
              <CheckCircle2 className="w-4 h-4 text-indigo-600 mt-0.5 shrink-0" />
              <div>
                <p className="font-semibold text-indigo-900 dark:text-indigo-200">Permitted Source Ingestion</p>
                <p className="text-indigo-700 dark:text-indigo-400 text-[11px] mt-0.5">
                  Greenhouse & Lever public API boards live. Aggressive scrapers blocked.
                </p>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 space-y-1">
              <div className="flex justify-between font-medium">
                <span>Verified Atomic Facts:</span>
                <span className="font-bold text-slate-900 dark:text-slate-100">24 confirmed</span>
              </div>
              <div className="flex justify-between font-medium">
                <span>Unconfirmed Candidates:</span>
                <span className="font-bold text-amber-600">4 pending review</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
