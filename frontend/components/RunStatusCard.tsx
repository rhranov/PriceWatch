"use client";

import { type AgentRun } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import { CheckCircle, XCircle, Loader2 } from "lucide-react";

export function RunStatusCard({ run }: { run: AgentRun }) {
  const isRunning = run.status === "running";

  return (
    <div className={`rounded-xl border p-4 flex items-center gap-4 ${
      run.status === "completed" ? "border-green-500/20 bg-green-500/5"
      : run.status === "failed" ? "border-red-500/20 bg-red-500/5"
      : "border-blue-500/20 bg-blue-500/5"
    }`}>
      {run.status === "completed" ? (
        <CheckCircle className="w-5 h-5 text-green-400 shrink-0" />
      ) : run.status === "failed" ? (
        <XCircle className="w-5 h-5 text-red-400 shrink-0" />
      ) : (
        <Loader2 className="w-5 h-5 text-blue-400 animate-spin shrink-0" />
      )}

      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium capitalize">
          {isRunning ? "Run in progress…" : `Last ${run.run_type} run — ${run.status}`}
        </div>
        <div className="text-xs text-muted-foreground mt-0.5">
          {timeAgo(run.started_at)} ·{" "}
          {run.products_checked} products checked ·{" "}
          {run.discoveries_found > 0 ? `${run.discoveries_found} new finds` : "No new discoveries"}
          {run.price_changes.length > 0 && ` · ${run.price_changes.length} price change(s)`}
        </div>
      </div>
    </div>
  );
}
