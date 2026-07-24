"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Discovery } from "@/lib/api";
import { formatEur, timeAgo } from "@/lib/utils";
import { Check, X, ExternalLink, Cpu, MemoryStick } from "lucide-react";
import { toast } from "sonner";
import { useState } from "react";

export default function DiscoveriesPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"pending" | "approved" | "rejected">("pending");

  const { data: discoveries = [], isLoading } = useQuery({
    queryKey: ["discoveries", tab],
    queryFn: () => api.discoveries.list(tab),
    refetchInterval: tab === "pending" ? 30_000 : undefined,
  });

  const reviewMutation = useMutation({
    mutationFn: ({ id, action, notes }: { id: string; action: "approve" | "reject"; notes?: string }) =>
      api.discoveries.review(id, action, notes),
    onSuccess: (_, { action }) => {
      toast.success(action === "approve" ? "Product added to watchlist!" : "Discovery rejected");
      qc.invalidateQueries({ queryKey: ["discoveries"] });
      qc.invalidateQueries({ queryKey: ["products"] });
    },
    onError: () => toast.error("Action failed"),
  });

  return (
    <div className="p-4 sm:p-6 space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold">Discoveries</h1>
        <p className="text-muted-foreground text-sm mt-0.5">
          New products found by the research agent — approve to add to the watchlist
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 rounded-lg bg-muted w-fit">
        {(["pending", "approved", "rejected"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors capitalize ${
              tab === t ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => <div key={i} className="h-40 rounded-xl bg-card animate-pulse" />)}
        </div>
      ) : discoveries.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground">
          <p className="text-4xl mb-3">🔍</p>
          <p>No {tab} discoveries</p>
          {tab === "pending" && (
            <p className="text-sm mt-1">The research agent checks for new products daily at 10:00 AM</p>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {discoveries.map((d) => (
            <DiscoveryCard
              key={d.id}
              discovery={d}
              showActions={tab === "pending"}
              onApprove={() => {
                if (window.confirm(`Add "${d.name}" to the watchlist?`)) {
                  reviewMutation.mutate({ id: d.id, action: "approve" });
                }
              }}
              onReject={() => {
                if (window.confirm(`Reject the discovery "${d.name}"?`)) {
                  reviewMutation.mutate({ id: d.id, action: "reject" });
                }
              }}
              loading={reviewMutation.isPending}
            />
          ))}
        </div>
      )}
    </div>
  );
}

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
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-start gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h3 className="font-semibold text-foreground">{d.name}</h3>
            {d.price_eur && (
              <span className="text-primary font-bold">{formatEur(d.price_eur)}</span>
            )}
            <span
              className={`text-xs px-2 py-0.5 rounded-full ${
                d.in_stock ? "bg-green-500/15 text-green-400" : "bg-red-500/15 text-red-400"
              }`}
            >
              {d.in_stock ? "In Stock" : "Out of Stock"}
            </span>
            {d.ships_to_germany && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-400">
                Ships to DE
              </span>
            )}
          </div>

          {/* Specs */}
          {Object.keys(d.specs).length > 0 && (
            <div className="flex flex-wrap gap-3 mt-2">
              {!!d.specs.unified_memory_gb && (
                <span className="flex items-center gap-1 text-xs text-muted-foreground">
                  <MemoryStick className="w-3 h-3" />
                  {d.specs.unified_memory_gb as number}GB Unified
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

          {/* AI Reasoning */}
          {d.ai_reasoning && (
            <p className="text-xs text-muted-foreground mt-2 italic border-l-2 border-primary/30 pl-3">
              {d.ai_reasoning}
            </p>
          )}

          <div className="flex items-center gap-3 mt-3 text-xs text-muted-foreground">
            {d.source_name && <span>Source: {d.source_name}</span>}
            <span>Found {timeAgo(d.found_at)}</span>
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

        {/* Actions */}
        {showActions && (
          <div className="flex gap-2 shrink-0">
            <button
              onClick={onReject}
              disabled={loading}
              className="p-2 rounded-lg border border-border hover:bg-red-500/10 hover:border-red-500/30 text-muted-foreground hover:text-red-400 transition-colors"
              title="Reject"
            >
              <X className="w-4 h-4" />
            </button>
            <button
              onClick={onApprove}
              disabled={loading}
              className="p-2 rounded-lg bg-primary/10 border border-primary/30 hover:bg-primary/20 text-primary transition-colors"
              title="Add to watchlist"
            >
              <Check className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Status badge for non-pending */}
        {!showActions && (
          <span className={`text-xs px-3 py-1 rounded-full capitalize ${
            d.status === "approved" ? "bg-green-500/15 text-green-400" : "bg-red-500/15 text-red-400"
          }`}>
            {d.status}
          </span>
        )}
      </div>
    </div>
  );
}
