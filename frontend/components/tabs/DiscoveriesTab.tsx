"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Discovery } from "@/lib/api";
import { formatEur, timeAgo } from "@/lib/utils";
import { Check, X, ExternalLink, Cpu, MemoryStick, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

type Filter = "pending" | "approved" | "rejected";

// ── Discovery card ─────────────────────────────────────────────────────────

function DiscoveryCard({
  discovery: d,
  showActions,
  onApprove,
  onReject,
  loading,
}: {
  discovery: Discovery;
  showActions: boolean;
  onApprove: () => void;
  onReject: () => void;
  loading: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border bg-card p-5 transition-colors",
        d.status === "approved"
          ? "border-green-500/20"
          : d.status === "rejected"
          ? "border-red-500/10 opacity-70"
          : "border-border",
      )}
    >
      <div className="flex items-start gap-4">
        <div className="flex-1 min-w-0">
          {/* Name + badges row */}
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-semibold text-foreground">{d.name}</h3>
            {d.price_eur && (
              <span className="text-primary font-bold text-sm">{formatEur(d.price_eur)}</span>
            )}
            <span
              className={cn(
                "text-xs px-2 py-0.5 rounded-full font-medium",
                d.in_stock
                  ? "bg-green-500/15 text-green-400"
                  : "bg-red-500/15 text-red-400",
              )}
            >
              {d.in_stock ? "In Stock" : "Out of Stock"}
            </span>
            {d.ships_to_germany && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-400">
                Ships DE
              </span>
            )}
          </div>

          {/* Specs */}
          {Object.keys(d.specs).length > 0 && (
            <div className="flex flex-wrap gap-3 mt-1.5">
              {!!d.specs.unified_memory_gb && (
                <span className="flex items-center gap-1 text-xs text-muted-foreground">
                  <MemoryStick className="w-3 h-3" />
                  {d.specs.unified_memory_gb as number}GB
                </span>
              )}
              {!!d.specs.chip && (
                <span className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Cpu className="w-3 h-3" />
                  {d.specs.chip as string}
                </span>
              )}
            </div>
          )}

          {/* AI reasoning */}
          {d.ai_reasoning && (
            <p className="text-xs text-muted-foreground mt-2 italic border-l-2 border-primary/30 pl-3 line-clamp-2">
              {d.ai_reasoning}
            </p>
          )}

          {/* Meta row */}
          <div className="flex items-center gap-3 mt-2.5 text-xs text-muted-foreground flex-wrap">
            {d.source_name && <span>{d.source_name}</span>}
            <span>{timeAgo(d.found_at)}</span>
            {d.source_url && (
              <a
                href={d.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 hover:text-foreground transition-colors"
              >
                View listing <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
        </div>

        {/* Actions / status */}
        <div className="shrink-0">
          {showActions ? (
            <div className="flex gap-2">
              <button
                onClick={onReject}
                disabled={loading}
                className="p-2 rounded-lg border border-border hover:bg-red-500/10 hover:border-red-500/30 text-muted-foreground hover:text-red-400 transition-colors disabled:opacity-50"
                title="Reject"
              >
                <X className="w-4 h-4" />
              </button>
              <button
                onClick={onApprove}
                disabled={loading}
                className="p-2 rounded-lg bg-primary/10 border border-primary/30 hover:bg-primary/20 text-primary transition-colors disabled:opacity-50"
                title="Add to watchlist"
              >
                <Check className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <span
              className={cn(
                "text-xs px-3 py-1 rounded-full capitalize font-medium",
                d.status === "approved"
                  ? "bg-green-500/15 text-green-400"
                  : "bg-red-500/15 text-red-400",
              )}
            >
              {d.status}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Tab ────────────────────────────────────────────────────────────────────

export function DiscoveriesTab() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<Filter>("pending");

  const { data: discoveries = [], isLoading } = useQuery({
    queryKey: ["discoveries", filter],
    queryFn: () => api.discoveries.list(filter),
    refetchInterval: filter === "pending" ? 30_000 : undefined,
  });

  const { data: pendingCount } = useQuery({
    queryKey: ["discoveries", "count"],
    queryFn: () => api.discoveries.countPending(),
    refetchInterval: 30_000,
  });

  const reviewMutation = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "approve" | "reject" }) =>
      api.discoveries.review(id, action),
    onSuccess: (_, { action }) => {
      toast.success(
        action === "approve" ? "Product added to watchlist!" : "Discovery rejected",
      );
      qc.invalidateQueries({ queryKey: ["discoveries"] });
      qc.invalidateQueries({ queryKey: ["products"] });
    },
    onError: () => toast.error("Action failed"),
  });

  const FILTERS: { id: Filter; label: string; count?: number }[] = [
    { id: "pending",  label: "Pending",  count: pendingCount?.count },
    { id: "approved", label: "Approved" },
    { id: "rejected", label: "Rejected" },
  ];

  return (
    <div className="space-y-5 max-w-4xl">
      <div>
        <h2 className="text-lg font-semibold text-foreground">Discoveries</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          New products found by the research agent — approve to add to the watchlist
        </p>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1 p-1 rounded-lg bg-muted w-fit">
        {FILTERS.map(({ id, label, count }) => (
          <button
            key={id}
            onClick={() => setFilter(id)}
            className={cn(
              "flex items-center gap-1.5 px-3 sm:px-4 py-1.5 rounded-md text-sm font-medium transition-colors",
              filter === id
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {label}
            {count ? (
              <span className="text-[10px] bg-yellow-500/20 text-yellow-400 rounded-full px-1.5 py-0.5 font-bold leading-none">
                {count}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      {/* List */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-36 rounded-xl bg-card animate-pulse" />
          ))}
        </div>
      ) : discoveries.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          <Sparkles className="w-10 h-10 mx-auto mb-3 opacity-20" />
          <p className="font-medium">No {filter} discoveries</p>
          {filter === "pending" && (
            <p className="text-sm mt-1 opacity-70">Run deep research to find new products</p>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {discoveries.map((d) => (
            <DiscoveryCard
              key={d.id}
              discovery={d}
              showActions={filter === "pending"}
              onApprove={() => reviewMutation.mutate({ id: d.id, action: "approve" })}
              onReject={() => reviewMutation.mutate({ id: d.id, action: "reject" })}
              loading={reviewMutation.isPending}
            />
          ))}
        </div>
      )}
    </div>
  );
}
