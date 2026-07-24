"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type SourceHealth } from "@/lib/api";
import { Globe, CheckCircle2, AlertTriangle, XCircle, Minus, Clock } from "lucide-react";
import { timeAgo } from "@/lib/utils";
import { cn } from "@/lib/utils";

// ── Health helpers ─────────────────────────────────────────────────────────

function healthMeta(status: SourceHealth["status"]) {
  switch (status) {
    case "healthy":
      return {
        label: "Healthy",
        color: "text-green-400",
        bg: "bg-green-500/10",
        border: "border-green-500/20",
        Icon: CheckCircle2,
      };
    case "degraded":
      return {
        label: "Degraded",
        color: "text-yellow-400",
        bg: "bg-yellow-500/10",
        border: "border-yellow-500/20",
        Icon: AlertTriangle,
      };
    case "failing":
      return {
        label: "Failing",
        color: "text-red-400",
        bg: "bg-red-500/10",
        border: "border-red-500/20",
        Icon: XCircle,
      };
    case "no_listings":
      return {
        label: "No listings",
        color: "text-muted-foreground",
        bg: "bg-muted/40",
        border: "border-border",
        Icon: Minus,
      };
  }
}

function SuccessBar({ rate }: { rate: number }) {
  const fill =
    rate >= 75 ? "bg-green-500" : rate >= 25 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-16 h-1 rounded-full bg-muted overflow-hidden shrink-0">
        <div
          className={cn("h-full rounded-full transition-all duration-500", fill)}
          style={{ width: `${rate}%` }}
        />
      </div>
      <span className="text-xs tabular-nums text-muted-foreground">{rate}%</span>
    </div>
  );
}

// ── Source health card ─────────────────────────────────────────────────────

function SourceHealthCard({ health: h }: { health: SourceHealth }) {
  const meta = healthMeta(h.status);
  const { Icon } = meta;

  return (
    <div
      className={cn(
        "rounded-xl border bg-card p-4 flex items-start gap-4 transition-opacity",
        !h.is_active && "opacity-50",
      )}
    >
      {/* Icon */}
      <div className="w-9 h-9 rounded-lg bg-muted flex items-center justify-center shrink-0 mt-0.5">
        <Globe className="w-4 h-4 text-muted-foreground" />
      </div>

      <div className="flex-1 min-w-0">
        {/* Name + status badge */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm text-foreground">{h.source_name}</span>
          <span
            className={cn(
              "flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border",
              meta.color, meta.bg, meta.border,
            )}
          >
            <Icon className="w-3 h-3 shrink-0" />
            {meta.label}
          </span>
          {!h.is_active && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
              Paused
            </span>
          )}
        </div>

        {/* Stats row */}
        <div className="flex items-center gap-4 mt-1.5 flex-wrap text-xs text-muted-foreground">
          {h.total_listings > 0 && (
            <>
              {h.success_rate_24h !== null && (
                <SuccessBar rate={h.success_rate_24h} />
              )}
              <span>
                {h.scraped_24h}/{h.total_listings} scraped 24h
              </span>
              {h.stale_listings > 0 && (
                <span className="text-orange-400">{h.stale_listings} stale</span>
              )}
              {h.never_scraped > 0 && (
                <span>{h.never_scraped} never scraped</span>
              )}
            </>
          )}
          <div className="flex items-center gap-1 ml-auto">
            <Clock className="w-3 h-3 shrink-0" />
            {h.last_success ? timeAgo(h.last_success) : "Never"}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Tab ────────────────────────────────────────────────────────────────────

export function SourcesTab() {
  const { data: healthData = [], isLoading } = useQuery({
    queryKey: ["sources-health"],
    queryFn: api.sources.health,
    refetchInterval: 60_000,
  });

  const healthy  = healthData.filter((h) => h.status === "healthy").length;
  const degraded = healthData.filter((h) => h.status === "degraded").length;
  const failing  = healthData.filter((h) => h.status === "failing").length;

  return (
    <div className="space-y-5 max-w-4xl">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Price Sources</h2>
          <p className="text-sm text-muted-foreground mt-0.5 flex flex-wrap gap-x-2">
            {healthy > 0  && <span className="text-green-400">{healthy} healthy</span>}
            {degraded > 0 && <span className="text-yellow-400">{degraded} degraded</span>}
            {failing > 0  && <span className="text-red-400">{failing} failing</span>}
            {healthData.length === 0 && !isLoading && <span>No sources configured</span>}
          </p>
        </div>

        {/* Alert pill */}
        {failing > 0 && (
          <div className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-red-500/10 text-red-400 border border-red-500/20 shrink-0">
            <XCircle className="w-3.5 h-3.5" />
            {failing} failing
          </div>
        )}
      </div>

      {/* Cards */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 rounded-xl bg-card animate-pulse" />
          ))}
        </div>
      ) : healthData.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          <Globe className="w-10 h-10 mx-auto mb-3 opacity-20" />
          <p className="font-medium">No sources configured</p>
          <p className="text-sm mt-1 opacity-70">Add sources via the Sources page</p>
        </div>
      ) : (
        <div className="space-y-3">
          {/* Failing first, then degraded, then healthy */}
          {[
            ...healthData.filter((h) => h.status === "failing"),
            ...healthData.filter((h) => h.status === "degraded"),
            ...healthData.filter((h) => h.status === "healthy"),
            ...healthData.filter((h) => h.status === "no_listings"),
          ].map((h) => (
            <SourceHealthCard key={h.source_id} health={h} />
          ))}
        </div>
      )}
    </div>
  );
}
