"use client";

import { useState, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatEur, timeAgo } from "@/lib/utils";
import { PriceChart } from "@/components/PriceChart";
import { StatusBadge } from "@/components/StatusBadge";
import { TrendingDown, TrendingUp, Package, Activity, Clock, AlertTriangle, GripVertical } from "lucide-react";
import { cn } from "@/lib/utils";

// ── Drag-to-reorder persistence ────────────────────────────────────────────

const ORDER_KEY = "pricewatch_product_order";

function loadOrder(): string[] {
  if (typeof window === "undefined") return [];
  try { return JSON.parse(localStorage.getItem(ORDER_KEY) ?? "[]"); }
  catch { return []; }
}

function saveOrder(ids: string[]) {
  localStorage.setItem(ORDER_KEY, JSON.stringify(ids));
}

function applyOrder(products: import("@/lib/api").Product[], savedIds: string[]): import("@/lib/api").Product[] {
  if (!savedIds.length) return products;
  const map = new Map(products.map((p) => [p.id, p]));
  const result: import("@/lib/api").Product[] = [];
  for (const id of savedIds) {
    const p = map.get(id);
    if (p) { result.push(p); map.delete(id); }
  }
  for (const p of map.values()) result.push(p);
  return result;
}

// ── Stat pill ──────────────────────────────────────────────────────────────

function StatPill({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  color?: "green" | "red" | "yellow";
}) {
  const valueColor =
    color === "green"  ? "text-green-400"  :
    color === "red"    ? "text-red-400"    :
    color === "yellow" ? "text-yellow-400" :
    "text-foreground";

  return (
    <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-card border border-border">
      <span className="text-muted-foreground shrink-0">{icon}</span>
      <div className="min-w-0">
        <p className="text-[11px] text-muted-foreground leading-none mb-1 truncate">{label}</p>
        <p className={cn("text-sm font-semibold tabular-nums truncate", valueColor)}>{value}</p>
      </div>
    </div>
  );
}

// ── Product card ───────────────────────────────────────────────────────────

function ProductCard({
  product,
  onDragStart,
  onDragOver,
  onDrop,
  isDragging,
}: {
  product: import("@/lib/api").Product;
  onDragStart: () => void;
  onDragOver: (e: React.DragEvent) => void;
  onDrop: () => void;
  isDragging: boolean;
}) {
  const { data: priceHistory = [] } = useQuery({
    queryKey: ["prices", product.id],
    queryFn: () => api.prices.forProduct(product.id, 30),
  });

  const { data: summaries = [] } = useQuery({
    queryKey: ["price-summary", product.id],
    queryFn: () => api.prices.summaryForProduct(product.id),
    refetchInterval: 60_000,
  });

  const activeListings = product.listings.filter((l) => l.is_active);

  const bestListing = activeListings
    .filter((l) => l.is_available && l.latest_price_eur)
    .sort((a, b) => (a.latest_price_eur ?? 0) - (b.latest_price_eur ?? 0))[0];

  const currPrice = bestListing?.latest_price_eur ?? null;

  const bestSummary =
    summaries.find((s) => s.listing_id === bestListing?.id) ??
    summaries.find((s) => s.current_price_eur != null);

  const isAllTimeLow = bestSummary?.is_all_time_low && bestSummary.is_available;
  const hasVerifiedPrice = activeListings.some((l) => l.last_verified_at);
  const isOld =
    bestListing?.last_verified_at &&
    Date.now() - new Date(bestListing.last_verified_at).getTime() > 48 * 3600_000;

  const chip = product.specs?.chip as string | undefined;
  const subtitle = [product.brand, chip ?? product.model].filter(Boolean).join(" · ");

  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onDragEnd={() => {}}
      className={cn(
        "rounded-xl border border-border bg-card p-5 flex flex-col gap-4 transition-opacity cursor-default select-none",
        isDragging && "opacity-40",
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        {/* Drag handle */}
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <GripVertical className="w-4 h-4 text-muted-foreground/40 shrink-0 cursor-grab active:cursor-grabbing" />
          <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-semibold text-foreground leading-tight">{product.name}</h3>
            {isAllTimeLow && (
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 uppercase tracking-wide shrink-0">
                ATL
              </span>
            )}
          </div>
          {subtitle && (
            <p className="text-xs text-muted-foreground mt-0.5 truncate">{subtitle}</p>
          )}
          {!hasVerifiedPrice && (
            <p className="text-[10px] text-muted-foreground/60 mt-1 italic">No verified price yet</p>
          )}
          </div>
        </div>

        <div className="text-right shrink-0">
          <div className="text-xl font-bold tabular-nums text-foreground">
            {formatEur(currPrice)}
          </div>
          {bestSummary?.change_pct != null && (
            <div
              className={cn(
                "text-xs flex items-center gap-0.5 justify-end mt-0.5 font-medium",
                bestSummary.change_pct < 0 ? "text-green-400" : "text-red-400",
              )}
            >
              {bestSummary.change_pct < 0
                ? <TrendingDown className="w-3 h-3" />
                : <TrendingUp className="w-3 h-3" />}
              {Math.abs(bestSummary.change_pct).toFixed(1)}% 7d
            </div>
          )}
          {isOld && (
            <p className="text-[10px] text-yellow-400/70 mt-0.5">
              {timeAgo(bestListing!.last_verified_at)}
            </p>
          )}
        </div>
      </div>

      {/* Chart */}
      {priceHistory.length > 0 && <PriceChart data={priceHistory} />}

      {/* Source pills */}
      <div className="flex flex-wrap gap-2">
        {activeListings.map((listing) => {
          const s = summaries.find((x) => x.listing_id === listing.id);
          return (
            <a
              key={listing.id}
              href={listing.listing_url}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(
                "flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-colors",
                listing.is_available
                  ? "border-green-500/20 bg-green-500/5 hover:bg-green-500/10"
                  : "border-border bg-muted hover:bg-muted/70",
              )}
            >
              <StatusBadge available={listing.is_available} />
              <span className="text-muted-foreground">{listing.source_name}</span>
              {listing.latest_price_eur && (
                <span className="font-medium text-foreground tabular-nums">
                  {formatEur(listing.latest_price_eur)}
                </span>
              )}
              {s?.is_all_time_low && s.is_available && (
                <span className="text-amber-400 font-bold">↓</span>
              )}
            </a>
          );
        })}
      </div>
    </div>
  );
}

// ── Tab ────────────────────────────────────────────────────────────────────

export function PricesTab() {
  const [order, setOrder] = useState<string[]>(() => loadOrder());
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const dragId = useRef<string | null>(null);

  const { data: products = [], isLoading } = useQuery({
    queryKey: ["products"],
    queryFn: () => api.products.list(),
    refetchInterval: 60_000,
  });

  const { data: latestPriceCheckRun } = useQuery({
    queryKey: ["runs", "latest", "price_check"],
    queryFn: () => api.runs.latestByType("price_check"),
    refetchInterval: 15_000,
  });

  const activeProducts = products.filter((p) => p.status === "active");
  const orderedProducts = applyOrder(activeProducts, order);
  const availableProducts = activeProducts.filter((p) =>
    p.listings.some((l) => l.is_available),
  );

  function handleDrop(targetId: string) {
    const src = dragId.current;
    if (!src || src === targetId) return;
    const ids = orderedProducts.map((p) => p.id);
    const from = ids.indexOf(src);
    const to   = ids.indexOf(targetId);
    if (from === -1 || to === -1) return;
    ids.splice(from, 1);
    ids.splice(to, 0, src);
    setOrder(ids);
    saveOrder(ids);
    dragId.current = null;
    setDraggingId(null);
  }

  const lastChecked = latestPriceCheckRun?.finished_at ?? latestPriceCheckRun?.started_at ?? null;
  const runIsStale =
    lastChecked && Date.now() - new Date(lastChecked).getTime() > 48 * 3600_000;

  return (
    <div className="space-y-5 max-w-7xl">
      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatPill
          icon={<Package className="w-3.5 h-3.5" />}
          label="Tracked"
          value={String(activeProducts.length)}
        />
        <StatPill
          icon={<Activity className="w-3.5 h-3.5 text-green-400" />}
          label="In Stock"
          value={String(availableProducts.length)}
          color="green"
        />
        <StatPill
          icon={<Clock className={cn("w-3.5 h-3.5", runIsStale ? "text-yellow-400" : "text-muted-foreground")} />}
          label="Last Check"
          value={latestPriceCheckRun ? timeAgo(lastChecked) : "Never"}
          color={runIsStale ? "yellow" : undefined}
        />
        <StatPill
          icon={<AlertTriangle className={cn("w-3.5 h-3.5", (latestPriceCheckRun?.errors?.length ?? 0) > 0 ? "text-red-400" : "text-muted-foreground")} />}
          label="Errors"
          value={String(latestPriceCheckRun?.errors?.length ?? 0)}
          color={(latestPriceCheckRun?.errors?.length ?? 0) > 0 ? "red" : undefined}
        />
      </div>

      {/* Stale warning */}
      {runIsStale && (
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-yellow-400 text-sm">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>
            Prices last verified {timeAgo(lastChecked)} — run a price check to refresh
          </span>
        </div>
      )}

      {/* Product grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-64 rounded-xl bg-card animate-pulse" />
          ))}
        </div>
      ) : activeProducts.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          <Package className="w-10 h-10 mx-auto mb-3 opacity-20" />
          <p className="font-medium">No products tracked yet</p>
          <p className="text-sm mt-1 opacity-70">Add products via the Products page</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {orderedProducts.map((product) => (
            <ProductCard
              key={product.id}
              product={product}
              isDragging={draggingId === product.id}
              onDragStart={() => { dragId.current = product.id; setDraggingId(product.id); }}
              onDragOver={(e) => { e.preventDefault(); }}
              onDrop={() => handleDrop(product.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
