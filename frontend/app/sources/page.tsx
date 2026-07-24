"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Source, type SourceHealth } from "@/lib/api";
import {
  Globe, Plus, ToggleLeft, ToggleRight, Trash2,
  CheckCircle2, AlertTriangle, XCircle, Clock, Minus,
} from "lucide-react";
import { toast } from "sonner";
import { Modal, FormField, Input, Select, Btn } from "@/components/Modal";
import { timeAgo } from "@/lib/utils";
import { cn } from "@/lib/utils";

// ── Health helpers ─────────────────────────────────────────────────────────

function healthMeta(status: SourceHealth["status"]) {
  switch (status) {
    case "healthy":     return { label: "Healthy",     color: "text-green-400",  bg: "bg-green-500/10",  border: "border-green-500/20",  Icon: CheckCircle2 };
    case "degraded":    return { label: "Degraded",    color: "text-yellow-400", bg: "bg-yellow-500/10", border: "border-yellow-500/20", Icon: AlertTriangle };
    case "failing":     return { label: "Failing",     color: "text-red-400",    bg: "bg-red-500/10",    border: "border-red-500/20",    Icon: XCircle };
    case "no_listings": return { label: "No listings", color: "text-muted-foreground", bg: "bg-muted/40", border: "border-border", Icon: Minus };
  }
}

function CoverageBar({ rate }: { rate: number | null }) {
  if (rate === null) return null;
  const color = rate >= 75 ? "bg-green-500" : rate >= 25 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 rounded-full bg-muted overflow-hidden">
        <div className={cn("h-full rounded-full", color)} style={{ width: `${rate}%` }} />
      </div>
      <span className="text-xs tabular-nums">{rate}%</span>
    </div>
  );
}

// ── New Source Modal ───────────────────────────────────────────────────────

function NewSourceModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [scraperType, setScraperType] = useState("playwright");
  const [rateLimit, setRateLimit] = useState("5");

  function autoSlug(s: string) {
    return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  }

  const save = useMutation({
    mutationFn: () =>
      api.sources.create({
        name,
        slug: slug || autoSlug(name),
        base_url: baseUrl,
        scraper_type: scraperType,
        rate_limit_seconds: parseFloat(rateLimit) || 5,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sources"] });
      qc.invalidateQueries({ queryKey: ["sources-health"] });
      toast.success("Source created");
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Modal open onClose={onClose} title="Add Price Source" description="Add a website to scrape for product prices.">
      <div className="space-y-4">
        <FormField label="Name">
          <Input
            value={name}
            onChange={(e) => { setName(e.target.value); if (!slug) setSlug(autoSlug(e.target.value)); }}
            placeholder="idealo.de"
          />
        </FormField>
        <FormField label="Slug" hint="Unique identifier used internally">
          <Input value={slug || autoSlug(name)} onChange={(e) => setSlug(e.target.value)} placeholder="idealo-de" />
        </FormField>
        <FormField label="Base URL">
          <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://www.idealo.de" />
        </FormField>
        <div className="grid grid-cols-2 gap-4">
          <FormField label="Scraper type">
            <Select value={scraperType} onChange={(e) => setScraperType(e.target.value)}>
              <option value="playwright">Playwright (JS-heavy sites)</option>
              <option value="httpx">httpx (static HTML)</option>
            </Select>
          </FormField>
          <FormField label="Rate limit (seconds)" hint="Min delay between requests">
            <Input type="number" value={rateLimit} onChange={(e) => setRateLimit(e.target.value)} min="1" max="60" />
          </FormField>
        </div>
        <p className="text-xs text-muted-foreground bg-muted/50 rounded-lg p-3">
          After adding a source, link it to one or more scopes via the Scopes page so the research agent uses it.
        </p>
        <div className="flex justify-end gap-3 pt-2 border-t border-border">
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn onClick={() => save.mutate()} loading={save.isPending} disabled={!name || !baseUrl}>
            Add source
          </Btn>
        </div>
      </div>
    </Modal>
  );
}

// ── Source Card ────────────────────────────────────────────────────────────

function SourceCard({
  src,
  health,
  onToggle,
  onDelete,
}: {
  src: Source;
  health: SourceHealth | undefined;
  onToggle: () => void;
  onDelete: () => void;
}) {
  const scraperTypeLabel: Record<string, string> = {
    playwright: "Playwright",
    httpx: "httpx",
  };

  const meta = health ? healthMeta(health.status) : null;
  const { Icon: HealthIcon } = meta ?? { Icon: Minus };

  return (
    <div className={cn("rounded-xl border bg-card p-4 flex items-start gap-4", !src.is_active && "opacity-60")}>
      <div className="w-9 h-9 rounded-lg bg-muted flex items-center justify-center shrink-0 mt-0.5">
        <Globe className="w-4 h-4 text-muted-foreground" />
      </div>

      <div className="flex-1 min-w-0">
        {/* Row 1: name + badges */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm">{src.name}</span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
            {scraperTypeLabel[src.scraper_type] ?? src.scraper_type}
          </span>
          <span className={cn(
            "text-xs px-2 py-0.5 rounded-full",
            src.is_active ? "bg-green-500/15 text-green-400" : "bg-muted text-muted-foreground"
          )}>
            {src.is_active ? "Active" : "Paused"}
          </span>
        </div>

        {/* Row 2: URL + rate limit */}
        <p className="text-xs text-muted-foreground mt-0.5">
          {src.base_url} · Rate limit: {src.rate_limit_seconds}s
        </p>

        {/* Row 3: health stats */}
        {health && meta && (
          <div className={cn(
            "mt-2 flex items-center flex-wrap gap-x-4 gap-y-1.5 rounded-lg border px-3 py-2",
            meta.bg, meta.border
          )}>
            {/* Status */}
            <div className={cn("flex items-center gap-1.5 text-xs font-medium", meta.color)}>
              <HealthIcon className="w-3.5 h-3.5 shrink-0" />
              {meta.label}
            </div>

            {/* Coverage bar */}
            {health.total_listings > 0 && (
              <div className={cn("flex items-center gap-2 text-xs text-muted-foreground")}>
                <CoverageBar rate={health.success_rate_24h} />
                <span>
                  {health.scraped_24h}/{health.total_listings} listings scraped 24h
                </span>
              </div>
            )}

            {/* Stale warning */}
            {health.stale_listings > 0 && health.status !== "no_listings" && (
              <span className="text-xs text-orange-400">
                {health.stale_listings} stale
              </span>
            )}

            {/* Never scraped */}
            {health.never_scraped > 0 && (
              <span className="text-xs text-muted-foreground">
                {health.never_scraped} never scraped
              </span>
            )}

            {/* Last success */}
            <div className="flex items-center gap-1 text-xs text-muted-foreground ml-auto">
              <Clock className="w-3 h-3" />
              {health.last_success ? `Last: ${timeAgo(health.last_success)}` : "Never scraped"}
            </div>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1 shrink-0">
        <button
          onClick={onToggle}
          className="p-2 rounded-lg hover:bg-muted text-muted-foreground transition-colors"
          title={src.is_active ? "Pause source" : "Enable source"}
        >
          {src.is_active
            ? <ToggleRight className="w-5 h-5 text-green-400" />
            : <ToggleLeft className="w-5 h-5" />}
        </button>
        <button
          onClick={onDelete}
          className="p-2 rounded-lg hover:bg-red-500/10 text-muted-foreground hover:text-red-400 transition-colors"
          title="Delete source"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────

export default function SourcesPage() {
  const qc = useQueryClient();
  const { data: sources = [], isLoading } = useQuery({
    queryKey: ["sources"],
    queryFn: api.sources.list,
  });
  const { data: healthData = [] } = useQuery({
    queryKey: ["sources-health"],
    queryFn: api.sources.health,
    refetchInterval: 60_000,
  });

  const healthById = Object.fromEntries(healthData.map((h) => [h.source_id, h]));

  const [createOpen, setCreateOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const toggleMutation = useMutation({
    mutationFn: (id: string) => api.sources.toggle(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sources"] });
      qc.invalidateQueries({ queryKey: ["sources-health"] });
      toast.success("Source toggled");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.sources.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sources"] });
      qc.invalidateQueries({ queryKey: ["sources-health"] });
      toast.success("Source deleted");
      setDeleteId(null);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const srcToDelete = deleteId ? sources.find((s) => s.id === deleteId) : null;

  // Summary counts for the header
  const failing = healthData.filter((h) => h.status === "failing").length;
  const degraded = healthData.filter((h) => h.status === "degraded").length;

  return (
    <div className="p-4 sm:p-6 space-y-6 max-w-3xl">
      {createOpen && <NewSourceModal onClose={() => setCreateOpen(false)} />}
      {deleteId && srcToDelete && (
        <Modal open onClose={() => setDeleteId(null)} title="Delete Source" width="max-w-sm">
          <p className="text-sm text-muted-foreground mb-4">
            Delete <strong>{srcToDelete.name}</strong>? This removes the source from all scopes and cannot be undone.
          </p>
          <div className="flex justify-end gap-3">
            <Btn variant="ghost" onClick={() => setDeleteId(null)}>Cancel</Btn>
            <Btn variant="danger" onClick={() => deleteMutation.mutate(deleteId)} loading={deleteMutation.isPending}>Delete</Btn>
          </div>
        </Modal>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Price Sources</h1>
          <p className="text-muted-foreground text-sm mt-0.5">
            Websites scraped for product prices.
            {failing > 0 && <span className="text-red-400 ml-1">{failing} failing.</span>}
            {degraded > 0 && <span className="text-yellow-400 ml-1">{degraded} degraded.</span>}
          </p>
        </div>
        <Btn onClick={() => setCreateOpen(true)}>
          <Plus className="w-4 h-4" /> Add Source
        </Btn>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => <div key={i} className="h-24 rounded-xl bg-card animate-pulse" />)}
        </div>
      ) : (
        <div className="space-y-3">
          {sources.map((src) => (
            <SourceCard
              key={src.id}
              src={src}
              health={healthById[src.id]}
              onToggle={() => toggleMutation.mutate(src.id)}
              onDelete={() => setDeleteId(src.id)}
            />
          ))}

          {sources.length === 0 && (
            <div className="rounded-xl border border-dashed border-border p-10 text-center text-muted-foreground">
              <Globe className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p className="font-medium">No sources configured</p>
              <p className="text-sm mt-1">Add a website to scrape for prices.</p>
              <Btn className="mx-auto mt-4" onClick={() => setCreateOpen(true)}>
                <Plus className="w-4 h-4" /> Add first source
              </Btn>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
