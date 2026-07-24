"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type DataCheck } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { CheckCircle, XCircle, Loader2, TrendingDown, TrendingUp, ShieldCheck, AlertTriangle, ChevronDown, ChevronUp, ExternalLink } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

export default function HistoryPage() {
  const { data: runs = [], isLoading } = useQuery({
    queryKey: ["runs"],
    queryFn: () => api.runs.list(50),
    refetchInterval: 15_000,
  });

  return (
    <div className="p-4 sm:p-6 space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold">Run History</h1>
        <p className="text-muted-foreground text-sm mt-0.5">
          Log of all agent pipeline executions
        </p>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => <div key={i} className="h-24 rounded-xl bg-card animate-pulse" />)}
        </div>
      ) : runs.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground">
          <p className="text-4xl mb-3">📋</p>
          <p>No runs yet</p>
          <p className="text-sm mt-1">The first run will happen at 10:00 AM Berlin time</p>
        </div>
      ) : (
        <div className="space-y-3">
          {runs.map((run) => (
            <RunCard key={run.id} run={run} />
          ))}
        </div>
      )}
    </div>
  );
}

function checkStatusMeta(status: string) {
  switch (status) {
    case "confirmed":   return { label: "Confirmed", color: "text-green-400",  bg: "bg-green-500/10",  icon: CheckCircle };
    case "changed":     return { label: "Changed",   color: "text-yellow-400", bg: "bg-yellow-500/10", icon: AlertTriangle };
    case "stale":       return { label: "Stale",     color: "text-orange-400", bg: "bg-orange-500/10", icon: AlertTriangle };
    case "dead_url":    return { label: "Dead URL",  color: "text-red-400",    bg: "bg-red-500/10",    icon: XCircle };
    case "error":       return { label: "Error",     color: "text-red-400",    bg: "bg-red-500/10",    icon: XCircle };
    case "now_in_stock":return { label: "Now in stock", color: "text-green-400", bg: "bg-green-500/10", icon: CheckCircle };
    default:            return { label: status,      color: "text-muted-foreground", bg: "bg-muted",   icon: ShieldCheck };
  }
}

function DataChecksPanel({ checks }: { checks: DataCheck[] }) {
  const problems = checks.filter((c) => c.status !== "confirmed");
  const confirmed = checks.filter((c) => c.status === "confirmed");

  return (
    <div className="mt-3 space-y-2">
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
        <ShieldCheck className="w-3.5 h-3.5" />
        Data integrity checks ({checks.length})
        {problems.length > 0 && (
          <span className="text-orange-400 font-normal">— {problems.length} need attention</span>
        )}
      </p>

      {/* Problems first */}
      {problems.map((c, i) => {
        const meta = checkStatusMeta(c.status ?? "");
        const Icon = meta.icon;
        return (
          <div key={i} className={cn("rounded-lg border px-3 py-2 text-xs", meta.bg,
            c.status === "changed" || c.status === "now_in_stock" ? "border-yellow-500/30" :
            c.status === "stale" ? "border-orange-500/30" : "border-red-500/30"
          )}>
            <div className="flex items-start gap-2">
              <Icon className={cn("w-3.5 h-3.5 mt-0.5 shrink-0", meta.color)} />
              <div className="flex-1 min-w-0">
                <span className="font-medium text-foreground">{c.product_name}</span>
                {c.source && <span className="text-muted-foreground"> · {c.source}</span>}
                <span className={cn("ml-2 px-1.5 py-0.5 rounded text-[10px] font-medium", meta.bg, meta.color)}>
                  {c.check_type === "watch_overdue" ? "Watch overdue"
                  : c.check_type === "signal_url_dead" ? "Source URL dead"
                  : c.check_type === "watch_url_dead" ? "Watch URL dead"
                  : c.check_type === "signal_stale" ? "Signal stale"
                  : meta.label}
                </span>
                {c.notes && <p className="text-muted-foreground mt-0.5">{c.notes}</p>}
                {c.previous_price_eur !== undefined && c.current_price_eur !== undefined &&
                 c.previous_price_eur !== c.current_price_eur && (
                  <p className="text-muted-foreground mt-0.5">
                    Price: €{c.previous_price_eur?.toLocaleString("de-DE")} → €{c.current_price_eur?.toLocaleString("de-DE")}
                  </p>
                )}
              </div>
              {c.url && (
                <a href={c.url} target="_blank" rel="noopener noreferrer"
                   className="text-primary hover:text-primary/80 shrink-0">
                  <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>
          </div>
        );
      })}

      {/* Confirmed — collapsed list */}
      {confirmed.length > 0 && (
        <div className="rounded-lg border border-border bg-green-500/5 px-3 py-2">
          <div className="flex items-center gap-1.5 text-xs text-green-400">
            <CheckCircle className="w-3.5 h-3.5" />
            <span className="font-medium">{confirmed.length} listing{confirmed.length !== 1 ? "s" : ""} verified correct</span>
          </div>
          <div className="mt-1 space-y-0.5">
            {confirmed.map((c, i) => (
              <p key={i} className="text-xs text-muted-foreground pl-5">
                {c.product_name}{c.source ? ` · ${c.source}` : ""}{c.notes ? ` — ${c.notes}` : ""}
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function formatDuration(startedAt: string, finishedAt: string | null): string | null {
  if (!finishedAt) return null;
  const sec = Math.round((new Date(finishedAt).getTime() - new Date(startedAt).getTime()) / 1000);
  if (sec <= 0) return null;
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  if (min < 60) return rem > 0 ? `${min}m ${rem}s` : `${min}m`;
  const hr = Math.floor(min / 60);
  const remMin = min % 60;
  return remMin > 0 ? `${hr}h ${remMin}m` : `${hr}h`;
}

function formatRunType(type: string): string {
  switch (type) {
    case "price_check": return "Price Check";
    case "deep_research": return "Deep Research";
    case "correction": return "Correction";
    default: return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }
}

function formatStatus(status: string): string {
  switch (status) {
    case "completed_with_errors": return "With Errors";
    default: return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }
}

function RunCard({ run }: { run: import("@/lib/api").AgentRun }) {
  const [showChecks, setShowChecks] = useState(false);
  const [showErrors, setShowErrors] = useState(false);
  const durationStr = formatDuration(run.started_at, run.finished_at);

  const hasChecks = run.data_checks?.length > 0;
  const checkProblems = run.data_checks?.filter((c) => c.status !== "confirmed").length ?? 0;

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-start gap-4">
        <div className="mt-0.5">
          {run.status === "completed" ? (
            <CheckCircle className="w-5 h-5 text-green-400" />
          ) : run.status === "failed" ? (
            <XCircle className="w-5 h-5 text-red-400" />
          ) : run.status === "completed_with_errors" ? (
            <AlertTriangle className="w-5 h-5 text-yellow-400" />
          ) : (
            <Loader2 className="w-5 h-5 text-blue-400 animate-spin" />
          )}
        </div>

        <div className="flex-1">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="font-medium">{formatRunType(run.run_type)}</span>
            <span className="text-xs text-muted-foreground">{formatDate(run.started_at)}</span>
            {durationStr && (
              <span className="text-xs text-muted-foreground">{durationStr}</span>
            )}
            <span className={`text-xs px-2 py-0.5 rounded-full ${
              run.status === "completed" ? "bg-green-500/15 text-green-400"
              : run.status === "failed" ? "bg-red-500/15 text-red-400"
              : run.status === "completed_with_errors" ? "bg-yellow-500/15 text-yellow-400"
              : "bg-blue-500/15 text-blue-400"
            }`}>
              {formatStatus(run.status)}
            </span>
          </div>

          {/* Stats */}
          <div className="flex flex-wrap gap-4 mt-2 text-sm text-muted-foreground">
            <span>{run.products_checked} checked</span>
            <span>{run.prices_updated} updated</span>
            {run.discoveries_found > 0 && (
              <span className="text-yellow-400">{run.discoveries_found} discoveries</span>
            )}
            {hasChecks && (
              <button
                onClick={() => setShowChecks((v) => !v)}
                className={cn(
                  "flex items-center gap-1 transition-colors",
                  checkProblems > 0 ? "text-orange-400 hover:text-orange-300" : "text-green-400 hover:text-green-300"
                )}
              >
                <ShieldCheck className="w-3.5 h-3.5" />
                {run.data_checks.length} integrity checks
                {checkProblems > 0 && ` · ${checkProblems} flagged`}
                {showChecks ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              </button>
            )}
            {run.errors.length > 0 && (
              <button
                onClick={() => setShowErrors((v) => !v)}
                className="flex items-center gap-1 text-red-400 hover:text-red-300 transition-colors"
              >
                <AlertTriangle className="w-3.5 h-3.5" />
                {run.errors.length} error{run.errors.length !== 1 ? "s" : ""}
                {showErrors ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              </button>
            )}
          </div>

          {/* Price changes */}
          {run.price_changes.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {run.price_changes.slice(0, 4).map((c, i) => (
                <span key={i} className={`text-xs flex items-center gap-1 px-2 py-0.5 rounded-full ${
                  c.direction === "↓" ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"
                }`}>
                  {c.direction === "↓" ? <TrendingDown className="w-3 h-3" /> : <TrendingUp className="w-3 h-3" />}
                  {c.title?.slice(0, 25)}… {c.change_pct > 0 ? "+" : ""}{c.change_pct}%
                </span>
              ))}
            </div>
          )}

          {/* Data integrity checks — expandable */}
          {showChecks && hasChecks && <DataChecksPanel checks={run.data_checks} />}

          {/* Errors — expandable */}
          {showErrors && run.errors.length > 0 && (
            <div className="mt-3 space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Errors ({run.errors.length})
              </p>
              {run.errors.map((err, i) => {
                const msg = typeof err === "string" ? err
                  : (err as { error?: string; message?: string })?.error
                  ?? (err as { error?: string; message?: string })?.message
                  ?? JSON.stringify(err);
                return (
                  <div key={i} className="rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2 text-xs text-red-400 font-mono break-all">
                    {msg}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
