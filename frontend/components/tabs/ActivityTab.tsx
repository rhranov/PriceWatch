"use client";

import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { timeAgo, formatDate } from "@/lib/utils";
import {
  CheckCircle, XCircle, Loader2,
  TrendingDown, TrendingUp, ChevronDown, ChevronUp,
  Activity, AlertTriangle,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ── Run card ───────────────────────────────────────────────────────────────

function RunCard({ run }: { run: import("@/lib/api").AgentRun }) {
  const [expanded, setExpanded] = useState(false);

  const durationSec = run.finished_at
    ? Math.round(
        (new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000,
      )
    : null;
  const duration = durationSec == null ? null
    : durationSec < 60  ? `${durationSec}s`
    : durationSec < 3600 ? `${Math.round(durationSec / 60)}m`
    : `${Math.round(durationSec / 3600)}h`;

  const hasDetails =
    run.price_changes.length > 0 || run.errors.length > 0;

  const statusDot =
    run.status === "completed"             ? "bg-green-400" :
    run.status === "completed_with_errors" ? "bg-yellow-400" :
    run.status === "failed"                ? "bg-red-400" :
                                             "bg-blue-400 animate-pulse";

  return (
    <div className="relative pl-10">
      {/* Timeline dot */}
      <div
        className={cn(
          "absolute left-3 top-4 w-2.5 h-2.5 rounded-full border-2 border-background shrink-0",
          statusDot,
        )}
      />

      <div className="rounded-xl border border-border bg-card p-4">
        <div className="flex items-start gap-3">
          {/* Run status icon */}
          <div className="mt-0.5 shrink-0">
            {run.status === "completed" ? (
              <CheckCircle className="w-4 h-4 text-green-400" />
            ) : run.status === "completed_with_errors" ? (
              <AlertTriangle className="w-4 h-4 text-yellow-400" />
            ) : run.status === "failed" ? (
              <XCircle className="w-4 h-4 text-red-400" />
            ) : (
              <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
            )}
          </div>

          <div className="flex-1 min-w-0">
            {/* Header row */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium text-sm capitalize">{run.run_type} run</span>
              <span
                className={cn(
                  "text-[10px] px-2 py-0.5 rounded-full font-medium uppercase",
                  run.status === "completed"             ? "bg-green-500/15 text-green-400" :
                  run.status === "completed_with_errors" ? "bg-yellow-500/15 text-yellow-400" :
                  run.status === "failed"                ? "bg-red-500/15 text-red-400" :
                                                          "bg-blue-500/15 text-blue-400",
                )}
              >
                {run.status}
              </span>
              <span className="text-xs text-muted-foreground hidden sm:inline">
                {formatDate(run.started_at)}
              </span>
              <span className="text-xs text-muted-foreground sm:hidden">
                {timeAgo(run.started_at)}
              </span>
              {duration && (
                <span className="text-xs text-muted-foreground">{duration}</span>
              )}
            </div>

            {/* Stats */}
            <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1 text-xs text-muted-foreground">
              <span>{run.products_checked} checked</span>
              <span>{run.prices_updated} updated</span>
              {run.discoveries_found > 0 && (
                <span className="text-yellow-400">{run.discoveries_found} discoveries</span>
              )}
              {run.errors.length > 0 && (
                <span className="text-red-400">{run.errors.length} errors</span>
              )}
            </div>
          </div>

          {/* Expand toggle */}
          {hasDetails && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="p-1 rounded text-muted-foreground hover:text-foreground transition-colors shrink-0"
            >
              {expanded
                ? <ChevronUp className="w-4 h-4" />
                : <ChevronDown className="w-4 h-4" />}
            </button>
          )}
        </div>

        {/* Expanded details */}
        {expanded && (
          <div className="mt-3 pt-3 border-t border-border space-y-1.5">
            {run.price_changes.map((c, i) => {
              const isDown = c.direction === "↓" || c.direction === "down";
              return (
                <div
                  key={i}
                  className={cn(
                    "flex items-center gap-2 text-xs px-2.5 py-1.5 rounded-lg",
                    isDown
                      ? "bg-green-500/8 text-green-400"
                      : "bg-red-500/8 text-red-400",
                  )}
                >
                  {isDown
                    ? <TrendingDown className="w-3.5 h-3.5 shrink-0" />
                    : <TrendingUp className="w-3.5 h-3.5 shrink-0" />}
                  <span className="font-medium truncate flex-1">{c.title}</span>
                  <span className="tabular-nums shrink-0">
                    {isDown ? "" : "+"}{c.change_pct}%
                  </span>
                </div>
              );
            })}
            {run.errors.length > 0 && (
              <div className="flex items-center gap-2 text-xs px-2.5 py-1.5 rounded-lg bg-red-500/8 text-red-400">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                <span>
                  {run.errors.length} scraper error{run.errors.length !== 1 ? "s" : ""} — see History for details
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Tab ────────────────────────────────────────────────────────────────────

function useRunCompletionNotifier(runs: import("@/lib/api").AgentRun[]) {
  const prevStatusMap = useRef<Record<string, string>>({});

  useEffect(() => {
    if (typeof window === "undefined") return;

    for (const run of runs) {
      const id = run.id.toString();
      const prev = prevStatusMap.current[id];
      const curr = run.status;

      if (prev === "running" && curr !== "running") {
        const label = run.run_type === "deep_research" ? "Deep Research" : "Price Check";
        const summary =
          curr === "completed"
            ? `${label} done — ${run.prices_updated} updated, ${run.discoveries_found} discoveries`
            : curr === "completed_with_errors"
            ? `${label} done with errors — ${run.errors.length} scraper error(s)`
            : `${label} failed`;

        if (Notification.permission === "granted") {
          new Notification("PriceWatch", { body: summary, icon: "/favicon.ico" });
        } else if (Notification.permission !== "denied") {
          Notification.requestPermission().then((p) => {
            if (p === "granted") new Notification("PriceWatch", { body: summary, icon: "/favicon.ico" });
          });
        }
      }

      prevStatusMap.current[id] = curr;
    }
  }, [runs]);
}

export function ActivityTab() {
  const { data: runs = [], isLoading } = useQuery({
    queryKey: ["runs"],
    queryFn: () => api.runs.list(50),
    refetchInterval: 15_000,
  });

  useRunCompletionNotifier(runs);

  const priceChangeCount = runs.reduce((n, r) => n + r.price_changes.length, 0);
  const errorCount       = runs.reduce((n, r) => n + r.errors.length, 0);

  return (
    <div className="space-y-5 max-w-4xl">
      {/* Header */}
      <div>
        <h2 className="text-lg font-semibold text-foreground">Activity</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          {runs.length > 0
            ? `${runs.length} runs · ${priceChangeCount} price changes · ${errorCount} errors`
            : "Price check runs and events"}
        </p>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 rounded-xl bg-card animate-pulse" />
          ))}
        </div>
      ) : runs.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          <Activity className="w-10 h-10 mx-auto mb-3 opacity-20" />
          <p className="font-medium">No runs yet</p>
          <p className="text-sm mt-1 opacity-70">Price check history will appear here</p>
        </div>
      ) : (
        <div className="relative">
          {/* Timeline spine */}
          <div className="absolute left-[15px] top-0 bottom-0 w-px bg-border" />
          <div className="space-y-3">
            {runs.map((run) => (
              <RunCard key={run.id} run={run} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
