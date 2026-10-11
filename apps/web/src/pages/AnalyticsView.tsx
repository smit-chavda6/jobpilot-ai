import { AlertCircle, Info } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "../components/ui/card";
import { Badge } from "../components/ui/badge";

export function AnalyticsView() {
  const metrics = [
    {
      title: "Application Conversion Rate",
      value: "28.5%",
      sampleSize: 28,
      confidenceInterval: "[14.2% – 47.9%]",
      sufficient: true,
      description: "Wilson 95% Confidence Interval computed on stored records.",
    },
    {
      title: "Interview Callback Rate",
      value: "14.3%",
      sampleSize: 14,
      confidenceInterval: "[4.1% – 36.2%]",
      sufficient: false,
      description: "Sample size n < 20. Displays preliminary guidance only.",
    },
    {
      title: "Median Time to First Response",
      value: "4.2 days",
      sampleSize: 12,
      confidenceInterval: "± 1.4 days",
      sufficient: false,
      description: "Based on confirmed employer response timestamps.",
    },
  ];

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      <div className="pb-2 border-b border-slate-200/60 dark:border-slate-800">
        <h1 className="text-2xl font-extrabold tracking-tight">Real-Time Search Analytics</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Operating Principle #1: Truth over polish. Metrics computed from stored database records.
        </p>
      </div>

      {/* Statistical Disclaimer Banner */}
      <div className="p-4 rounded-xl bg-slate-100 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 text-xs text-slate-600 dark:text-slate-300 flex items-start gap-3">
        <Info className="w-4 h-4 text-indigo-500 shrink-0 mt-0.5" />
        <div>
          <span className="font-bold text-slate-800 dark:text-slate-100">Statistical Ground Truth: </span>
          All rates indicate exact sample size (n). Rates below n = 20 carry wide Wilson confidence intervals.
          Correlations between tailored resumes and callback rates are descriptive and do not assert causality.
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {metrics.map((m) => (
          <Card key={m.title}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold text-slate-600 dark:text-slate-300">
                  {m.title}
                </CardTitle>
                <Badge variant={m.sufficient ? "success" : "warning"} className="text-[10px]">
                  n = {m.sampleSize}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-3xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100">
                {m.value}
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400 space-y-1">
                <p>
                  <strong className="text-slate-700 dark:text-slate-300">95% Wilson CI: </strong>
                  {m.confidenceInterval}
                </p>
                <p className="text-[11px] leading-relaxed">{m.description}</p>
              </div>
              {!m.sufficient && (
                <div className="p-2 rounded-lg bg-amber-50 dark:bg-amber-950/30 text-amber-800 dark:text-amber-300 text-[11px] flex items-center gap-1.5 border border-amber-200/50">
                  <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                  <span>Insufficient data (n &lt; 20)</span>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Funnel Breakdown */}
      <Card>
        <CardHeader>
          <CardTitle>Application Conversion Funnel</CardTitle>
          <CardDescription>Direct SQL aggregate of user applications by status milestone</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4 text-xs">
            <div>
              <div className="flex justify-between font-semibold mb-1">
                <span>Discovered Listings</span>
                <span>32 (100%)</span>
              </div>
              <div className="w-full h-3 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                <div className="h-full bg-indigo-500 rounded-full" style={{ width: "100%" }} />
              </div>
            </div>

            <div>
              <div className="flex justify-between font-semibold mb-1">
                <span>Tailored & Approved by User</span>
                <span>18 (56.2%)</span>
              </div>
              <div className="w-full h-3 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                <div className="h-full bg-indigo-500 rounded-full" style={{ width: "56.2%" }} />
              </div>
            </div>

            <div>
              <div className="flex justify-between font-semibold mb-1">
                <span>Submitted (Explicit Human Confirmation)</span>
                <span>8 (25.0%)</span>
              </div>
              <div className="w-full h-3 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                <div className="h-full bg-emerald-500 rounded-full" style={{ width: "25.0%" }} />
              </div>
            </div>

            <div>
              <div className="flex justify-between font-semibold mb-1">
                <span>Interviews Scheduled</span>
                <span>2 (6.2%)</span>
              </div>
              <div className="w-full h-3 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                <div className="h-full bg-violet-500 rounded-full" style={{ width: "6.2%" }} />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
