"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Scope } from "@/lib/api";
import { Layers, Package, Tag, Plus, Pencil, Trash2, Link2, Unlink, ChevronDown, ChevronUp, Clock, AlertCircle } from "lucide-react";
import { timeAgo } from "@/lib/utils";
import { toast } from "sonner";
import { Modal, FormField, Input, Textarea, Btn } from "@/components/Modal";

// ── Helpers ────────────────────────────────────────────────────────────────

function slugify(s: string) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function parseTerms(s: string): string[] {
  return s.split("\n").map((t) => t.trim()).filter(Boolean);
}

// ── Scope Form Modal ───────────────────────────────────────────────────────

interface ScopeFormProps {
  initial?: Scope;
  onClose: () => void;
}

function ScopeFormModal({ initial, onClose }: ScopeFormProps) {
  const qc = useQueryClient();
  const isEdit = !!initial;

  const [name, setName] = useState(initial?.name ?? "");
  const [slug, setSlug] = useState(initial?.slug ?? "");
  const [desc, setDesc] = useState(initial?.description ?? "");
  const [rulesJson, setRulesJson] = useState(
    initial ? JSON.stringify(initial.qualifier_rules, null, 2) : '{\n  "must_ship_to_germany": true\n}'
  );
  const [terms, setTerms] = useState((initial?.search_terms ?? []).join("\n"));
  const [minPrice, setMinPrice] = useState(initial?.min_price_eur?.toString() ?? "");
  const [maxPrice, setMaxPrice] = useState(initial?.max_price_eur?.toString() ?? "");
  const [rulesError, setRulesError] = useState("");

  const save = useMutation({
    mutationFn: async () => {
      let rules: Record<string, unknown>;
      try { rules = JSON.parse(rulesJson); } catch {
        setRulesError("Invalid JSON"); throw new Error("Invalid JSON");
      }
      setRulesError("");
      const payload = {
        name,
        slug: isEdit ? undefined : (slug || slugify(name)),
        description: desc || null,
        qualifier_rules: rules,
        search_terms: parseTerms(terms),
        min_price_eur: minPrice ? parseFloat(minPrice) : null,
        max_price_eur: maxPrice ? parseFloat(maxPrice) : null,
      };
      if (isEdit) return api.scopes.update(initial.id, payload);
      return api.scopes.create({ ...payload, slug: slug || slugify(name) });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scopes"] });
      toast.success(isEdit ? "Scope updated" : "Scope created");
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Modal
      open
      onClose={onClose}
      title={isEdit ? "Edit Scope" : "New Scope"}
      description="Define what kinds of products to track and how to find them."
      width="max-w-2xl"
    >
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <FormField label="Name">
            <Input
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (!isEdit && !slug) setSlug(slugify(e.target.value));
              }}
              placeholder="Gaming GPUs"
            />
          </FormField>
          <FormField label="Slug" hint="URL-safe identifier, set once">
            <Input
              value={slug || (!isEdit ? slugify(name) : initial?.slug)}
              onChange={(e) => setSlug(e.target.value)}
              disabled={isEdit}
              placeholder="gaming-gpus"
            />
          </FormField>
        </div>

        <FormField label="Description">
          <Input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="What products does this scope track?" />
        </FormField>

        <div className="grid grid-cols-2 gap-4">
          <FormField label="Min price (€)" hint="Optional">
            <Input type="number" value={minPrice} onChange={(e) => setMinPrice(e.target.value)} placeholder="0" />
          </FormField>
          <FormField label="Max price (€)" hint="Optional">
            <Input type="number" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)} placeholder="10000" />
          </FormField>
        </div>

        <FormField
          label="Qualification rules (JSON)"
          hint="The AI uses these rules to decide if a found product belongs to this scope."
        >
          <Textarea
            rows={6}
            value={rulesJson}
            onChange={(e) => { setRulesJson(e.target.value); setRulesError(""); }}
            className={rulesError ? "border-red-500" : ""}
          />
          {rulesError && <p className="text-xs text-red-500">{rulesError}</p>}
        </FormField>

        <FormField
          label="Search terms (one per line)"
          hint="Terms the research agent will search on each linked source and X.com."
        >
          <Textarea
            rows={5}
            value={terms}
            onChange={(e) => setTerms(e.target.value)}
            placeholder={"128GB unified memory mini PC\nNVIDIA DGX Spark\nAMD Ryzen AI Max 395"}
          />
        </FormField>

        <div className="flex justify-end gap-3 pt-2 border-t border-border">
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn onClick={() => save.mutate()} loading={save.isPending}>
            {isEdit ? "Save changes" : "Create scope"}
          </Btn>
        </div>
      </div>
    </Modal>
  );
}

// ── Source Link Modal ──────────────────────────────────────────────────────

function SourcesModal({ scope, onClose }: { scope: Scope; onClose: () => void }) {
  const qc = useQueryClient();
  const { data: allSources = [] } = useQuery({ queryKey: ["sources"], queryFn: api.sources.list });
  const { data: linked = [] } = useQuery({
    queryKey: ["scope-sources", scope.id],
    queryFn: () => api.scopes.listSources(scope.id),
  });

  const linkedIds = new Set(linked.map((l) => l.source_id));

  const link = useMutation({
    mutationFn: (sourceId: string) => api.scopes.linkSource(scope.id, sourceId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["scope-sources", scope.id] }); toast.success("Source linked"); },
    onError: (e: Error) => toast.error(e.message),
  });

  const unlink = useMutation({
    mutationFn: (sourceId: string) => api.scopes.unlinkSource(scope.id, sourceId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["scope-sources", scope.id] }); toast.success("Source removed"); },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Modal open onClose={onClose} title={`Sources — ${scope.name}`} description="Control which sites the research agent searches for this scope.">
      <div className="space-y-3">
        {allSources.map((src) => {
          const isLinked = linkedIds.has(src.id);
          return (
            <div key={src.id} className="flex items-center justify-between p-3 rounded-lg border border-border bg-muted/30">
              <div>
                <p className="text-sm font-medium">{src.name}</p>
                <p className="text-xs text-muted-foreground">{src.base_url}</p>
              </div>
              {isLinked ? (
                <Btn
                  variant="ghost"
                  onClick={() => unlink.mutate(src.id)}
                  loading={unlink.isPending}
                  className="text-red-400 hover:text-red-300"
                >
                  <Unlink className="w-3.5 h-3.5" /> Remove
                </Btn>
              ) : (
                <Btn variant="ghost" onClick={() => link.mutate(src.id)} loading={link.isPending}>
                  <Link2 className="w-3.5 h-3.5" /> Link
                </Btn>
              )}
            </div>
          );
        })}
        {allSources.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-4">No sources configured yet.</p>
        )}
      </div>
    </Modal>
  );
}

// ── Delete Confirm ─────────────────────────────────────────────────────────

function DeleteScopeModal({ scope, onClose }: { scope: Scope; onClose: () => void }) {
  const qc = useQueryClient();
  const del = useMutation({
    mutationFn: () => api.scopes.delete(scope.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["scopes"] }); toast.success("Scope deleted"); onClose(); },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <Modal open onClose={onClose} title="Delete scope?" description={`"${scope.name}" and all its products will be permanently removed.`}>
      <div className="flex justify-end gap-3 pt-2">
        <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
        <Btn variant="danger" onClick={() => del.mutate()} loading={del.isPending}>Delete</Btn>
      </div>
    </Modal>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────

export default function ScopesPage() {
  const { data: scopes = [], isLoading } = useQuery({ queryKey: ["scopes"], queryFn: api.scopes.list });
  const { data: latestPriceCheckRun } = useQuery({
    queryKey: ["runs", "latest", "price_check"],
    queryFn: () => api.runs.latestByType("price_check"),
    refetchInterval: 60_000,
  });
  const { data: pendingDiscoveries = [] } = useQuery({
    queryKey: ["discoveries", "pending"],
    queryFn: () => api.discoveries.list("pending"),
    refetchInterval: 60_000,
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [editScope, setEditScope] = useState<Scope | null>(null);
  const [deleteScope, setDeleteScope] = useState<Scope | null>(null);
  const [sourcesScope, setSourcesScope] = useState<Scope | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const qc = useQueryClient();

  const toggle = useMutation({
    mutationFn: (s: Scope) => api.scopes.update(s.id, { is_active: !s.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scopes"] }),
  });

  return (
    <div className="p-4 sm:p-6 space-y-6 max-w-4xl">
      {/* Modals */}
      {createOpen && <ScopeFormModal onClose={() => setCreateOpen(false)} />}
      {editScope && <ScopeFormModal initial={editScope} onClose={() => setEditScope(null)} />}
      {deleteScope && <DeleteScopeModal scope={deleteScope} onClose={() => setDeleteScope(null)} />}
      {sourcesScope && <SourcesModal scope={sourcesScope} onClose={() => setSourcesScope(null)} />}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Product Scopes</h1>
          <p className="text-muted-foreground text-sm mt-0.5">
            Categories of products to track. Each scope defines qualification rules, search terms, and linked price sources.
          </p>
        </div>
        <Btn onClick={() => setCreateOpen(true)}>
          <Plus className="w-4 h-4" /> New Scope
        </Btn>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => <div key={i} className="h-40 rounded-xl bg-card animate-pulse" />)}
        </div>
      ) : (
        <div className="space-y-4">
          {scopes.map((scope) => (
            <ScopeCard
              key={scope.id}
              scope={scope}
              expanded={expandedId === scope.id}
              onToggleExpand={() => setExpandedId(expandedId === scope.id ? null : scope.id)}
              onEdit={() => setEditScope(scope)}
              onDelete={() => setDeleteScope(scope)}
              onManageSources={() => setSourcesScope(scope)}
              onToggleActive={() => toggle.mutate(scope)}
              latestPriceCheckRun={latestPriceCheckRun ?? null}
              pendingCount={pendingDiscoveries.filter((d) => d.scope_id === scope.id).length}
            />
          ))}

          {scopes.length === 0 && (
            <div className="rounded-xl border border-dashed border-border p-10 text-center text-muted-foreground">
              <Layers className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p className="font-medium">No scopes yet</p>
              <p className="text-sm mt-1">Create a scope to start tracking a product category.</p>
              <Btn className="mx-auto mt-4" onClick={() => setCreateOpen(true)}>
                <Plus className="w-4 h-4" /> Create first scope
              </Btn>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Scope Card ─────────────────────────────────────────────────────────────

function ScopeCard({
  scope, expanded, onToggleExpand, onEdit, onDelete, onManageSources, onToggleActive,
  latestPriceCheckRun, pendingCount,
}: {
  scope: Scope;
  expanded: boolean;
  onToggleExpand: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onManageSources: () => void;
  onToggleActive: () => void;
  latestPriceCheckRun: import("@/lib/api").AgentRun | null;
  pendingCount: number;
}) {
  const { data: linked = [] } = useQuery({
    queryKey: ["scope-sources", scope.id],
    queryFn: () => api.scopes.listSources(scope.id),
  });
  const activeSourceCount = linked.filter((s) => s.is_active).length;

  return (
    <div className={`rounded-xl border bg-card ${!scope.is_active ? "opacity-60" : ""}`}>
      {/* Header */}
      <div className="flex items-start gap-4 p-5">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <Layers className="w-4 h-4 text-primary shrink-0" />
            <h2 className="text-base font-semibold">{scope.name}</h2>
            <button
              onClick={onToggleActive}
              className={`text-xs px-2 py-0.5 rounded-full transition-colors ${
                scope.is_active
                  ? "bg-green-500/15 text-green-400 hover:bg-green-500/25"
                  : "bg-muted text-muted-foreground hover:bg-muted/80"
              }`}
            >
              {scope.is_active ? "Active" : "Paused"}
            </button>
          </div>
          {scope.description && (
            <p className="text-sm text-muted-foreground mt-1.5 line-clamp-2">{scope.description}</p>
          )}
          <div className="flex gap-4 mt-2 text-xs text-muted-foreground flex-wrap">
            <span className="flex items-center gap-1"><Package className="w-3 h-3" />{scope.product_count} products</span>
            <span className="flex items-center gap-1"><Tag className="w-3 h-3" />{scope.search_terms.length} search terms</span>
            {activeSourceCount > 0 && (
              <span className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
                {activeSourceCount} source{activeSourceCount !== 1 ? "s" : ""}
              </span>
            )}
            {latestPriceCheckRun && (
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                checked {timeAgo(latestPriceCheckRun.finished_at ?? latestPriceCheckRun.started_at)}
              </span>
            )}
            {pendingCount > 0 && (
              <span className="flex items-center gap-1 text-yellow-400">
                <AlertCircle className="w-3 h-3" />
                {pendingCount} pending discover{pendingCount !== 1 ? "ies" : "y"}
              </span>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 shrink-0">
          <button onClick={onManageSources} title="Manage price sources" className="p-2 rounded-lg hover:bg-muted text-muted-foreground transition-colors">
            <Link2 className="w-4 h-4" />
          </button>
          <button onClick={onEdit} title="Edit scope" className="p-2 rounded-lg hover:bg-muted text-muted-foreground transition-colors">
            <Pencil className="w-4 h-4" />
          </button>
          <button onClick={onDelete} title="Delete scope" className="p-2 rounded-lg hover:bg-muted text-red-400 transition-colors">
            <Trash2 className="w-4 h-4" />
          </button>
          <button onClick={onToggleExpand} title="Show details" className="p-2 rounded-lg hover:bg-muted text-muted-foreground transition-colors">
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="border-t border-border px-5 pb-5 pt-4 space-y-4">
          {Object.keys(scope.qualifier_rules).length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-2">Qualification Rules</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(scope.qualifier_rules)
                  .filter(([k]) => k !== "description" && k !== "disqualifiers")
                  .map(([k, v]) => (
                    <span key={k} className="text-xs px-2.5 py-1 rounded-full bg-muted border border-border">
                      {k.replace(/_/g, " ")}: <span className="text-foreground">{String(v)}</span>
                    </span>
                  ))}
              </div>
            </div>
          )}

          {scope.search_terms.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-2">Search Terms</p>
              <div className="flex flex-wrap gap-1.5">
                {scope.search_terms.map((term, i) => (
                  <span key={i} className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary border border-primary/20">{term}</span>
                ))}
              </div>
            </div>
          )}

          {linked.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-2">Linked Price Sources</p>
              <div className="flex flex-wrap gap-2">
                {linked.map((s) => (
                  <span key={s.id} className="text-xs px-2.5 py-1 rounded-full bg-muted border border-border flex items-center gap-1.5">
                    <span className={`w-1.5 h-1.5 rounded-full ${s.is_active ? "bg-green-400" : "bg-muted-foreground"}`} />
                    {s.source_name}
                  </span>
                ))}
              </div>
            </div>
          )}

          {(scope.min_price_eur || scope.max_price_eur) && (
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">Price Range</p>
              <p className="text-sm">
                {scope.min_price_eur ? `€${scope.min_price_eur.toLocaleString("de-DE")}` : "—"}
                {" – "}
                {scope.max_price_eur ? `€${scope.max_price_eur.toLocaleString("de-DE")}` : "no limit"}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
