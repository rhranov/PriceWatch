"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Product } from "@/lib/api";
import { formatEur } from "@/lib/utils";
import { StatusBadge } from "@/components/StatusBadge";
import { PriceChart } from "@/components/PriceChart";
import { Modal, FormField, Input, Textarea, Select, Btn } from "@/components/Modal";
import { Pause, Play, ExternalLink, Plus, Pencil, Trash2, Link2 } from "lucide-react";
import { toast } from "sonner";

// ── Product Form Modal ─────────────────────────────────────────────────────

function ProductFormModal({
  initial,
  onClose,
}: {
  initial?: Product;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const isEdit = !!initial;
  const { data: scopes = [] } = useQuery({ queryKey: ["scopes"], queryFn: api.scopes.list });

  const [scopeId, setScopeId] = useState(initial?.scope_id ?? scopes[0]?.id ?? "");
  const [name, setName] = useState(initial?.name ?? "");
  const [brand, setBrand] = useState(initial?.brand ?? "");
  const [model, setModel] = useState(initial?.model ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [imageUrl, setImageUrl] = useState(initial?.image_url ?? "");
  // Specs as key-value pairs
  const [specPairs, setSpecPairs] = useState<{ k: string; v: string }[]>(
    initial
      ? Object.entries(initial.specs).map(([k, v]) => ({ k, v: String(v) }))
      : [{ k: "", v: "" }]
  );

  const addSpec = () => setSpecPairs((p) => [...p, { k: "", v: "" }]);
  const removeSpec = (i: number) => setSpecPairs((p) => p.filter((_, j) => j !== i));
  const updateSpec = (i: number, field: "k" | "v", val: string) =>
    setSpecPairs((p) => p.map((sp, j) => (j === i ? { ...sp, [field]: val } : sp)));

  const save = useMutation({
    mutationFn: () => {
      const specs = Object.fromEntries(
        specPairs.filter((sp) => sp.k.trim()).map(({ k, v }) => {
          const num = parseFloat(v);
          return [k.trim(), isNaN(num) ? v : num];
        })
      );
      const payload = {
        scope_id: scopeId || scopes[0]?.id,
        name,
        brand: brand || null,
        model: model || null,
        notes: notes || null,
        image_url: imageUrl || null,
        specs,
      };
      if (isEdit) return api.products.update(initial.id, payload);
      return api.products.create(payload);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["products"] });
      toast.success(isEdit ? "Product updated" : "Product created");
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Modal
      open
      onClose={onClose}
      title={isEdit ? "Edit Product" : "Add Product"}
      description="Track a specific product and its price listings."
      width="max-w-2xl"
    >
      <div className="space-y-4">
        <FormField label="Scope">
          <Select value={scopeId} onChange={(e) => setScopeId(e.target.value)}>
            {scopes.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </Select>
        </FormField>

        <FormField label="Product name">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="NVIDIA DGX Spark" />
        </FormField>

        <div className="grid grid-cols-2 gap-4">
          <FormField label="Brand" hint="Optional">
            <Input value={brand} onChange={(e) => setBrand(e.target.value)} placeholder="NVIDIA" />
          </FormField>
          <FormField label="Model" hint="Optional">
            <Input value={model} onChange={(e) => setModel(e.target.value)} placeholder="DGX Spark" />
          </FormField>
        </div>

        {/* Specs */}
        <div className="space-y-1.5">
          <label className="text-sm font-medium">Specs</label>
          <div className="space-y-2">
            {specPairs.map((sp, i) => (
              <div key={i} className="flex gap-2">
                <Input
                  value={sp.k}
                  onChange={(e) => updateSpec(i, "k", e.target.value)}
                  placeholder="key (e.g. unified_memory_gb)"
                  className="flex-1"
                />
                <Input
                  value={sp.v}
                  onChange={(e) => updateSpec(i, "v", e.target.value)}
                  placeholder="value"
                  className="flex-1"
                />
                <button
                  onClick={() => removeSpec(i)}
                  className="px-2 text-muted-foreground hover:text-red-400 transition-colors"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          <button onClick={addSpec} className="text-xs text-primary hover:underline mt-1">
            + Add spec
          </button>
        </div>

        <FormField label="Notes" hint="Optional internal notes">
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Any notes about this product..." />
        </FormField>

        <FormField label="Image URL" hint="Optional product image">
          <Input value={imageUrl} onChange={(e) => setImageUrl(e.target.value)} placeholder="https://..." />
        </FormField>

        <div className="flex justify-end gap-3 pt-2 border-t border-border">
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn onClick={() => save.mutate()} loading={save.isPending} disabled={!name || !scopeId}>
            {isEdit ? "Save changes" : "Add product"}
          </Btn>
        </div>
      </div>
    </Modal>
  );
}

// ── Add Listing Modal ──────────────────────────────────────────────────────

function AddListingModal({ product, onClose }: { product: Product; onClose: () => void }) {
  const qc = useQueryClient();
  const { data: sources = [] } = useQuery({ queryKey: ["sources"], queryFn: api.sources.list });
  const [sourceId, setSourceId] = useState(sources[0]?.id ?? "");
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [isPrimary, setIsPrimary] = useState(false);

  const add = useMutation({
    mutationFn: () =>
      api.products.addListing(product.id, {
        source_id: sourceId || sources[0]?.id,
        listing_url: url,
        listing_title: title || undefined,
        is_primary: isPrimary,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["products"] });
      toast.success("Listing added — will be price-checked on next run");
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Modal
      open
      onClose={onClose}
      title={`Add listing — ${product.name}`}
      description="Add a URL where this product is sold. It will be scraped on the next run."
    >
      <div className="space-y-4">
        <FormField label="Source (website)">
          <Select value={sourceId} onChange={(e) => setSourceId(e.target.value)}>
            {sources.map((s) => (
              <option key={s.id} value={s.id}>{s.name} — {s.base_url}</option>
            ))}
          </Select>
        </FormField>

        <FormField label="Listing URL">
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.amazon.de/dp/B0ABC123"
          />
        </FormField>

        <FormField label="Listing title" hint="Optional — leave blank to auto-detect">
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Auto-detected on first scrape" />
        </FormField>

        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={isPrimary} onChange={(e) => setIsPrimary(e.target.checked)} className="rounded" />
          Mark as primary listing
        </label>

        <div className="flex justify-end gap-3 pt-2 border-t border-border">
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn onClick={() => add.mutate()} loading={add.isPending} disabled={!url || !sourceId}>
            Add listing
          </Btn>
        </div>
      </div>
    </Modal>
  );
}

// ── Delete Confirm ─────────────────────────────────────────────────────────

function DeleteProductModal({ product, onClose }: { product: Product; onClose: () => void }) {
  const qc = useQueryClient();
  const del = useMutation({
    mutationFn: () => api.products.delete(product.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["products"] });
      toast.success("Product deleted");
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <Modal open onClose={onClose} title="Delete product?" description={`"${product.name}" and all its price history will be permanently removed.`}>
      <div className="flex justify-end gap-3 pt-2">
        <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
        <Btn variant="danger" onClick={() => del.mutate()} loading={del.isPending}>Delete</Btn>
      </div>
    </Modal>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────

export default function ProductsPage() {
  const qc = useQueryClient();
  const { data: products = [], isLoading } = useQuery({
    queryKey: ["products"],
    queryFn: () => api.products.list(),
    refetchInterval: 60_000,
  });
  const { data: scopes = [] } = useQuery({ queryKey: ["scopes"], queryFn: api.scopes.list });

  const [createOpen, setCreateOpen] = useState(false);
  const [editProduct, setEditProduct] = useState<Product | null>(null);
  const [deleteProduct, setDeleteProduct] = useState<Product | null>(null);
  const [listingProduct, setListingProduct] = useState<Product | null>(null);
  const [filterScope, setFilterScope] = useState("");

  const toggleMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api.products.update(id, { status: status === "active" ? "paused" : "active" }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["products"] }); toast.success("Updated"); },
  });

  const filtered = filterScope ? products.filter((p) => p.scope_id === filterScope) : products;

  return (
    <div className="p-4 sm:p-6 space-y-6 max-w-5xl">
      {/* Modals */}
      {createOpen && <ProductFormModal onClose={() => setCreateOpen(false)} />}
      {editProduct && <ProductFormModal initial={editProduct} onClose={() => setEditProduct(null)} />}
      {deleteProduct && <DeleteProductModal product={deleteProduct} onClose={() => setDeleteProduct(null)} />}
      {listingProduct && <AddListingModal product={listingProduct} onClose={() => setListingProduct(null)} />}

      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold">Products</h1>
          <p className="text-muted-foreground text-sm mt-0.5">
            Tracked products and their price listings across all sources
          </p>
        </div>
        <div className="flex items-center gap-3">
          {scopes.length > 0 && (
            <select
              value={filterScope}
              onChange={(e) => setFilterScope(e.target.value)}
              className="text-sm px-3 py-1.5 rounded-lg border border-border bg-card"
            >
              <option value="">All scopes</option>
              {scopes.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          )}
          <Btn onClick={() => setCreateOpen(true)}>
            <Plus className="w-4 h-4" /> Add Product
          </Btn>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => <div key={i} className="h-48 rounded-xl bg-card animate-pulse" />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground border border-dashed border-border rounded-xl">
          <p className="text-3xl mb-3">📦</p>
          <p className="font-medium">No products yet</p>
          <p className="text-sm mt-1">Add a product manually or approve a discovery.</p>
          <Btn className="mx-auto mt-4" onClick={() => setCreateOpen(true)}>
            <Plus className="w-4 h-4" /> Add first product
          </Btn>
        </div>
      ) : (
        <div className="space-y-4">
          {filtered.map((p) => (
            <ProductRow
              key={p.id}
              product={p}
              scopeName={scopes.find((s) => s.id === p.scope_id)?.name}
              onToggle={() => toggleMutation.mutate({ id: p.id, status: p.status })}
              onEdit={() => setEditProduct(p)}
              onDelete={() => setDeleteProduct(p)}
              onAddListing={() => setListingProduct(p)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Product Row ────────────────────────────────────────────────────────────

function ProductRow({
  product: p,
  scopeName,
  onToggle,
  onEdit,
  onDelete,
  onAddListing,
}: {
  product: Product;
  scopeName?: string;
  onToggle: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onAddListing: () => void;
}) {
  const { data: prices = [] } = useQuery({
    queryKey: ["prices", p.id],
    queryFn: () => api.prices.forProduct(p.id, 60),
  });

  const isPaused = p.status === "paused";

  return (
    <div className={`rounded-xl border bg-card p-5 ${isPaused ? "opacity-60" : ""}`}>
      <div className="flex items-start gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h3 className="font-semibold">{p.name}</h3>
            {p.brand && <span className="text-xs text-muted-foreground">{p.brand}</span>}
            {scopeName && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
                {scopeName}
              </span>
            )}
            <span className={`text-xs px-2 py-0.5 rounded-full capitalize ${isPaused ? "bg-muted text-muted-foreground" : "bg-green-500/15 text-green-400"}`}>
              {p.status}
            </span>
          </div>

          {/* Specs */}
          <div className="flex flex-wrap gap-3 mt-1.5 text-xs text-muted-foreground">
            {Object.entries(p.specs).slice(0, 5).map(([k, v]) => (
              <span key={k}>{k.replace(/_/g, " ")}: <span className="text-foreground">{String(v)}</span></span>
            ))}
          </div>

          {/* Price chart */}
          {prices.length > 1 && <div className="mt-3"><PriceChart data={prices} height={80} /></div>}

          {/* Listings */}
          <div className="flex flex-wrap gap-2 mt-3 items-center">
            {p.listings.filter((l) => l.is_active).map((l) => (
              <a
                key={l.id}
                href={l.listing_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border border-border bg-muted hover:bg-accent/10 transition-colors"
              >
                <StatusBadge available={l.is_available} />
                {l.source_name}
                {l.latest_price_eur && ` · ${formatEur(l.latest_price_eur)}`}
                <ExternalLink className="w-2.5 h-2.5 text-muted-foreground" />
              </a>
            ))}
            <button
              onClick={onAddListing}
              className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-full border border-dashed border-border text-muted-foreground hover:text-foreground hover:border-border transition-colors"
            >
              <Plus className="w-3 h-3" /> Add source
            </button>
          </div>

          {p.lowest_price_eur && (
            <p className="text-xs text-muted-foreground mt-2">
              Lowest: <span className="text-foreground font-medium">{formatEur(p.lowest_price_eur)}</span>
            </p>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1 shrink-0">
          <button onClick={onAddListing} title="Add price source" className="p-2 rounded-lg hover:bg-muted text-muted-foreground transition-colors">
            <Link2 className="w-4 h-4" />
          </button>
          <button onClick={onEdit} title="Edit product" className="p-2 rounded-lg hover:bg-muted text-muted-foreground transition-colors">
            <Pencil className="w-4 h-4" />
          </button>
          <button onClick={onDelete} title="Delete product" className="p-2 rounded-lg hover:bg-muted text-red-400 transition-colors">
            <Trash2 className="w-4 h-4" />
          </button>
          <button
            onClick={onToggle}
            className="p-2 rounded-lg border border-border hover:bg-muted transition-colors text-muted-foreground"
            title={isPaused ? "Resume monitoring" : "Pause monitoring"}
          >
            {isPaused ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
          </button>
        </div>
      </div>
    </div>
  );
}
