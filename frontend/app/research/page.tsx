"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type ResearchSignal, type ResearchWatch } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import {
  Rocket,
  Megaphone,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  BarChart2,
  Eye,
  Globe,
  Clock,
  CheckCircle,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Users,
  Zap,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useState } from "react";
import { toast } from "sonner";

// ── Config ─────────────────────────────────────────────────────────────────

const SIGNAL_TYPES = [
  { key: "all",                     label: "All",           idleClass: "bg-muted text-muted-foreground border-transparent",                     activeClass: "bg-primary/10 text-primary border-primary/30" },
  { key: "product_launch",          label: "Launches",      idleClass: "bg-blue-500/8 text-blue-400/70 border-blue-500/15",                      activeClass: "bg-blue-500/20 text-blue-300 border-blue-500/40" },
  { key: "product_announcement",    label: "Announcements", idleClass: "bg-purple-500/8 text-purple-400/70 border-purple-500/15",                activeClass: "bg-purple-500/20 text-purple-300 border-purple-500/40" },
  { key: "price_increase",          label: "Price ↑",       idleClass: "bg-red-500/8 text-red-400/70 border-red-500/15",                         activeClass: "bg-red-500/20 text-red-300 border-red-500/40" },
  { key: "price_decrease",          label: "Price ↓",       idleClass: "bg-green-500/8 text-green-400/70 border-green-500/15",                   activeClass: "bg-green-500/20 text-green-300 border-green-500/40" },
  { key: "price_change",            label: "Price Change",  idleClass: "bg-teal-500/8 text-teal-400/70 border-teal-500/15",                      activeClass: "bg-teal-500/20 text-teal-300 border-teal-500/40" },
  { key: "market_trend",            label: "Trends",        idleClass: "bg-yellow-500/8 text-yellow-400/70 border-yellow-500/15",                activeClass: "bg-yellow-500/20 text-yellow-300 border-yellow-500/40" },
  { key: "market_intelligence",     label: "Market Intel",  idleClass: "bg-violet-500/8 text-violet-400/70 border-violet-500/15",                activeClass: "bg-violet-500/20 text-violet-300 border-violet-500/40" },
  { key: "supply_issue",            label: "Supply",        idleClass: "bg-orange-500/8 text-orange-400/70 border-orange-500/15",                activeClass: "bg-orange-500/20 text-orange-300 border-orange-500/40" },
  { key: "new_competitor",          label: "Competitor",    idleClass: "bg-cyan-500/8 text-cyan-400/70 border-cyan-500/15",                      activeClass: "bg-cyan-500/20 text-cyan-300 border-cyan-500/40" },
  { key: "product_discontinuation", label: "Discontinued",  idleClass: "bg-red-500/8 text-red-400/70 border-red-500/15",                         activeClass: "bg-red-500/20 text-red-300 border-red-500/40" },
  { key: "competitor_intel",        label: "Intel",         idleClass: "bg-muted/60 text-muted-foreground/70 border-transparent",                activeClass: "bg-muted text-foreground border-border" },
] as const;

type SignalTypeKey = (typeof SIGNAL_TYPES)[number]["key"];


function signalMeta(type: string) {
  switch (type) {
    case "product_launch":
      return { icon: Rocket, color: "text-blue-400", bg: "bg-blue-500/10", border: "border-blue-500/20", label: "Launch" };
    case "product_announcement":
      return { icon: Megaphone, color: "text-purple-400", bg: "bg-purple-500/10", border: "border-purple-500/20", label: "Announcement" };
    case "price_increase":
      return { icon: TrendingUp, color: "text-red-400", bg: "bg-red-500/10", border: "border-red-500/20", label: "Price ↑" };
    case "price_decrease":
      return { icon: TrendingDown, color: "text-green-400", bg: "bg-green-500/10", border: "border-green-500/20", label: "Price ↓" };
    case "market_trend":
      return { icon: BarChart2, color: "text-yellow-400", bg: "bg-yellow-500/10", border: "border-yellow-500/20", label: "Market Trend" };
    case "supply_issue":
      return { icon: AlertTriangle, color: "text-orange-400", bg: "bg-orange-500/10", border: "border-orange-500/20", label: "Supply" };
    case "availability_change":
      return { icon: Globe, color: "text-teal-400", bg: "bg-teal-500/10", border: "border-teal-500/20", label: "Availability" };
    case "price_change":
      return { icon: Zap, color: "text-teal-400", bg: "bg-teal-500/10", border: "border-teal-500/20", label: "Price Change" };
    case "new_competitor":
      return { icon: Users, color: "text-cyan-400", bg: "bg-cyan-500/10", border: "border-cyan-500/20", label: "Competitor" };
    case "market_intelligence":
      return { icon: BarChart2, color: "text-violet-400", bg: "bg-violet-500/10", border: "border-violet-500/20", label: "Market Intel" };
    case "product_discontinuation":
      return { icon: XCircle, color: "text-red-400", bg: "bg-red-500/10", border: "border-red-500/20", label: "Discontinued" };
    default:
      return { icon: Eye, color: "text-muted-foreground", bg: "bg-muted", border: "border-border", label: "Intel" };
  }
}

function platformFromUrl(url: string | null, fallback: string | null): string {
  if (!url) return fallback ?? "Source";
  try {
    const host = new URL(url).hostname.replace(/^www\./, "");
    if (host.includes("tomshardware.com")) return "Tom's Hardware";
    if (host.includes("x.com") || host.includes("twitter.com")) return "X / Twitter";
    if (host.includes("nvidianews.nvidia.com")) return "NVIDIA Newsroom";
    if (host.includes("nvidia.com")) return "NVIDIA";
    if (host.includes("amd.com")) return "AMD";
    if (host.includes("macworld.com")) return "Macworld";
    if (host.includes("apple.com")) return "Apple";
    if (host.includes("trendforce.com")) return "TrendForce";
    if (host.includes("servethehome.com")) return "ServeTheHome";
    if (host.includes("videocardz.com")) return "Videocardz";
    if (host.includes("anandtech.com")) return "AnandTech";
    if (host.includes("theverge.com")) return "The Verge";
    if (host.includes("arstechnica.com")) return "Ars Technica";
    if (host.includes("notebookcheck.net")) return "NotebookCheck";
    // fallback: show the bare hostname
    return host;
  } catch {
    return fallback ?? "Source";
  }
}

function significanceBadge(sig: string) {
  switch (sig) {
    case "critical": return "bg-red-500/20 text-red-300 border-red-500/30";
    case "high": return "bg-orange-500/20 text-orange-300 border-orange-500/30";
    case "medium": return "bg-blue-500/20 text-blue-300 border-blue-500/30";
    default: return "bg-muted text-muted-foreground border-border";
  }
}

function watchTypeMeta(type: string) {
  switch (type) {
    case "check_price": return { label: "Check price", icon: TrendingUp };
    case "check_availability": return { label: "Check availability", icon: Globe };
    case "check_launch": return { label: "Check launch", icon: Rocket };
    case "check_eu_availability": return { label: "Check EU availability", icon: Globe };
    case "search_x": return { label: "Search X", icon: Eye };
    default: return { label: "Search news", icon: Eye };
  }
}

function daysUntil(dateStr: string | null): number | null {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  const now = new Date();
  const diff = Math.ceil((d.getTime() - now.getTime()) / 86_400_000);
  return diff;
}

// ── Signal card ────────────────────────────────────────────────────────────

function SignalCard({ signal }: { signal: ResearchSignal }) {
  const [expanded, setExpanded] = useState(false);
  const qc = useQueryClient();
  const meta = signalMeta(signal.signal_type);
  const Icon = meta.icon;

  const statusMutation = useMutation({
    mutationFn: (status: string) => api.research.updateSignal(signal.id, { status }),
    onSuccess: () => {
      toast.success("Updated");
      qc.invalidateQueries({ queryKey: ["research-signals"] });
    },
  });

  const isExpired = signal.status === "expired";

  return (
    <div
      className={cn(
        "rounded-xl border p-4 space-y-3 transition-opacity",
        meta.border,
        meta.bg,
        isExpired && "opacity-50"
      )}
    >
      {/* Header row */}
      <div className="flex items-start gap-3">
        <div className={cn("mt-0.5 w-7 h-7 rounded-lg flex items-center justify-center shrink-0", meta.bg, "border", meta.border)}>
          <Icon className={cn("w-3.5 h-3.5", meta.color)} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={cn("text-xs px-2 py-0.5 rounded-full border font-medium", meta.bg, meta.color, meta.border)}>
              {meta.label}
            </span>
            <span className={cn("text-xs px-2 py-0.5 rounded-full border capitalize", significanceBadge(signal.significance))}>
              {signal.significance}
            </span>
          </div>
          <h3 className="font-semibold text-foreground mt-1.5 text-sm leading-snug">{signal.title}</h3>
          <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground flex-wrap">
            <span>{timeAgo(signal.discovered_at)}</span>
            {signal.source_platform && !signal.source_url && (
              <>
                <span>·</span>
                <span>{platformFromUrl(null, signal.source_platform)}</span>
              </>
            )}
            {signal.source_author && (
              <>
                <span>·</span>
                <span>{signal.source_author}</span>
              </>
            )}
          </div>
        </div>

        <button
          onClick={() => setExpanded((v) => !v)}
          className="text-muted-foreground hover:text-foreground transition-colors shrink-0"
        >
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
      </div>

      {/* Summary — always visible */}
      {signal.summary && (
        <p className="text-xs text-muted-foreground leading-relaxed pl-10">{signal.summary}</p>
      )}

      {/* Source link — always visible, prominent */}
      {signal.source_url && (
        <div className="pl-10">
          <a
            href={signal.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className={cn(
              "inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border font-medium transition-opacity hover:opacity-75",
              meta.bg, meta.color, meta.border
            )}
          >
            <ExternalLink className="w-3 h-3 shrink-0" />
            {`Open on ${platformFromUrl(signal.source_url, signal.source_platform)}`}
            {signal.source_author && (
              <span className="opacity-60 font-normal">· {signal.source_author}</span>
            )}
          </a>
        </div>
      )}

      {/* Expanded details */}
      {expanded && (
        <div className="pl-10 space-y-3">
          {signal.action_description && (
            <div className="p-2.5 rounded-lg bg-yellow-500/5 border border-yellow-500/20 text-xs text-yellow-200">
              <span className="font-semibold">Action: </span>{signal.action_description}
            </div>
          )}

          {signal.follow_up_date && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Clock className="w-3.5 h-3.5" />
              Follow-up: <span className="text-foreground font-medium">{signal.follow_up_date}</span>
            </div>
          )}

          {signal.watches.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Watching for</p>
              {signal.watches.map((w) => (
                <WatchItem key={w.id} watch={w} compact />
              ))}
            </div>
          )}

          {signal.notes && (
            <p className="text-xs text-muted-foreground italic">{signal.notes}</p>
          )}

          {/* Status actions */}
          {signal.status !== "expired" && signal.status !== "acted_on" && (
            <div className="flex gap-2 pt-1">
              {signal.status === "new" && (
                <button
                  onClick={() => statusMutation.mutate("watching")}
                  className="text-xs px-3 py-1 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
                >
                  Mark watching
                </button>
              )}
              <button
                onClick={() => statusMutation.mutate("acted_on")}
                className="text-xs px-3 py-1 rounded-lg bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors"
              >
                Mark done
              </button>
              <button
                onClick={() => statusMutation.mutate("expired")}
                className="text-xs px-3 py-1 rounded-lg bg-muted text-muted-foreground hover:bg-muted/80 transition-colors"
              >
                Expire
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Watch item ─────────────────────────────────────────────────────────────

function WatchItem({ watch, compact = false }: { watch: ResearchWatch; compact?: boolean }) {
  const qc = useQueryClient();
  const meta = watchTypeMeta(watch.watch_type);
  const Icon = meta.icon;
  const days = daysUntil(watch.check_by_date);

  const doneMutation = useMutation({
    mutationFn: () =>
      api.research.updateWatch(watch.id, { status: "done", last_checked_at: new Date().toISOString() }),
    onSuccess: () => {
      toast.success("Watch marked done");
      qc.invalidateQueries({ queryKey: ["research-watches"] });
    },
  });

  const urgency =
    days === null ? "" :
    days < 0 ? "border-red-500/40 bg-red-500/5" :
    days <= 2 ? "border-orange-500/40 bg-orange-500/5" :
    days <= 7 ? "border-yellow-500/40 bg-yellow-500/5" :
    "border-border bg-card";

  if (compact) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Icon className="w-3 h-3 shrink-0" />
        <span className="flex-1">{watch.title}</span>
        {watch.check_by_date && (
          <span className={cn(
            "px-1.5 py-0.5 rounded text-xs",
            days !== null && days < 0 ? "text-red-400" :
            days !== null && days <= 2 ? "text-orange-400" : "text-muted-foreground"
          )}>
            {watch.check_by_date}
          </span>
        )}
      </div>
    );
  }

  return (
    <div className={cn("rounded-lg border p-3 space-y-2", urgency)}>
      <div className="flex items-start gap-2">
        <Icon className="w-3.5 h-3.5 mt-0.5 text-muted-foreground shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium">{watch.title}</p>
          {watch.description && (
            <p className="text-xs text-muted-foreground mt-0.5">{watch.description}</p>
          )}
          {watch.search_query && (
            <p className="text-xs text-muted-foreground mt-0.5 font-mono">&ldquo;{watch.search_query}&rdquo;</p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {watch.check_by_date && (
            <div className="text-right">
              <p className={cn(
                "text-xs font-medium",
                days !== null && days < 0 ? "text-red-400" :
                days !== null && days <= 2 ? "text-orange-400" :
                days !== null && days <= 7 ? "text-yellow-400" : "text-muted-foreground"
              )}>
                {days !== null && days < 0 ? `${Math.abs(days)}d overdue` :
                 days === 0 ? "Today!" :
                 days === 1 ? "Tomorrow" :
                 `${days}d`}
              </p>
              <p className="text-xs text-muted-foreground">{watch.check_by_date}</p>
            </div>
          )}
          {watch.target_url && (
            <a href={watch.target_url} target="_blank" rel="noopener noreferrer"
               className="text-primary hover:text-primary/80">
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}
          <button
            onClick={() => doneMutation.mutate()}
            className="p-1 rounded hover:bg-green-500/20 text-muted-foreground hover:text-green-400 transition-colors"
            title="Mark done"
          >
            <CheckCircle className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function ResearchPage() {
  const [typeFilter, setTypeFilter] = useState<SignalTypeKey>("all");
  const [showExpired, setShowExpired] = useState(false);

  const { data: signals = [], isLoading: signalsLoading } = useQuery({
    queryKey: ["research-signals", typeFilter],
    queryFn: () =>
      api.research.listSignals({
        signal_type: typeFilter === "all" ? undefined : typeFilter,
        limit: 100,
      }),
    refetchInterval: 60_000,
  });

  const { data: latestSignals = [] } = useQuery({
    queryKey: ["research-signals-latest"],
    queryFn: () => api.research.listSignals({ limit: 1 }),
    refetchInterval: 300_000,
  });
  const lastUpdatedAt = latestSignals[0]?.discovered_at ?? null;

  const { data: watches = [], isLoading: watchesLoading } = useQuery({
    queryKey: ["research-watches"],
    queryFn: () => api.research.listWatches("pending"),
    refetchInterval: 60_000,
  });

  const visibleSignals = showExpired
    ? signals
    : signals.filter((s) => s.status !== "expired");

  const newCount = signals.filter((s) => s.status === "new").length;
  const watchDueCount = watches.filter((w) => {
    const days = daysUntil(w.check_by_date);
    return days !== null && days <= 3;
  }).length;

  return (
    <div className="p-4 sm:p-6 space-y-6 max-w-6xl">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">Research Intelligence</h1>
          <p className="text-muted-foreground text-sm mt-0.5">
            Market signals, product announcements, and upcoming research tasks
          </p>
          {lastUpdatedAt && (
            <p className="text-xs text-muted-foreground/60 mt-1">
              Last signal: {timeAgo(lastUpdatedAt)}
            </p>
          )}
        </div>
        <div className="flex gap-3 text-sm">
          {newCount > 0 && (
            <span className="px-3 py-1.5 rounded-full bg-primary/10 text-primary font-medium">
              {newCount} new signal{newCount !== 1 ? "s" : ""}
            </span>
          )}
          {watchDueCount > 0 && (
            <span className="px-3 py-1.5 rounded-full bg-orange-500/10 text-orange-400 font-medium">
              {watchDueCount} due soon
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-[1fr_320px] gap-6 items-start">
        {/* ── Left: signal feed ── */}
        <div className="space-y-4">
          {/* Type filter */}
          <div className="flex gap-1.5 flex-wrap">
            {SIGNAL_TYPES.map(({ key, label, idleClass, activeClass }) => (
              <button
                key={key}
                onClick={() => setTypeFilter(key)}
                className={cn(
                  "px-3 py-1.5 rounded-lg text-xs font-medium transition-all border",
                  typeFilter === key ? activeClass : idleClass
                )}
              >
                {label}
              </button>
            ))}
            <button
              onClick={() => setShowExpired((v) => !v)}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ml-auto",
                showExpired ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {showExpired ? "Hide expired" : "Show expired"}
            </button>
          </div>

          {/* Feed */}
          {signalsLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-28 rounded-xl bg-card animate-pulse" />
              ))}
            </div>
          ) : visibleSignals.length === 0 ? (
            <div className="text-center py-20 text-muted-foreground">
              <Eye className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p className="font-medium">No signals yet</p>
              <p className="text-sm mt-1">
                Research signals appear here after each daily run
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {visibleSignals.map((signal) => (
                <SignalCard key={signal.id} signal={signal} />
              ))}
            </div>
          )}
        </div>

        {/* ── Right: upcoming watches ── */}
        <div className="space-y-4 sticky top-6">
          <div>
            <h2 className="text-sm font-semibold text-foreground">Up Next</h2>
            <p className="text-xs text-muted-foreground mt-0.5">Items to check in upcoming runs</p>
          </div>

          {watchesLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => <div key={i} className="h-16 rounded-lg bg-card animate-pulse" />)}
            </div>
          ) : watches.length === 0 ? (
            <div className="text-center py-10 text-muted-foreground text-xs">
              <Clock className="w-6 h-6 mx-auto mb-2 opacity-30" />
              No pending watch items
            </div>
          ) : (
            <div className="space-y-2">
              {watches.map((w) => (
                <WatchItem key={w.id} watch={w} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
