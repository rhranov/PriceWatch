/**
 * API client — all fetch calls to the FastAPI backend.
 * Uses Next.js rewrites so /api/* → localhost:8000/api/*
 */

const BASE = "/api";

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`API ${path}: ${res.status} ${error}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Types ──────────────────────────────────────────────────────────────────

export interface Scope {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  qualifier_rules: Record<string, unknown>;
  search_terms: string[];
  min_price_eur: number | null;
  max_price_eur: number | null;
  is_active: boolean;
  product_count: number;
  created_at: string;
}

export interface Source {
  id: string;
  name: string;
  slug: string;
  base_url: string;
  scraper_type: string;
  is_active: boolean;
  rate_limit_seconds: number;
  config: Record<string, unknown>;
  created_at: string;
}

export interface SourceHealth {
  source_id: string;
  source_name: string;
  source_slug: string;
  base_url: string;
  is_active: boolean;
  total_listings: number;
  scraped_24h: number;
  scraped_7d: number;
  never_scraped: number;
  stale_listings: number;
  success_rate_24h: number | null;
  last_success: string | null;
  status: "healthy" | "degraded" | "failing" | "no_listings";
}

export interface ScopeSource {
  id: string;
  source_id: string;
  source_name: string;
  source_slug: string;
  base_url: string;
  search_url_template: string | null;
  is_active: boolean;
}

export interface Listing {
  id: string;
  source_id: string;
  source_name: string;
  listing_url: string;
  listing_title: string | null;
  is_primary: boolean;
  is_active: boolean;
  last_scraped_at: string | null;
  last_verified_at: string | null;
  is_available: boolean | null;
  latest_price_eur: number | null;
}

export interface Product {
  id: string;
  scope_id: string;
  name: string;
  brand: string | null;
  model: string | null;
  specs: Record<string, unknown>;
  status: string;
  notes: string | null;
  image_url: string | null;
  added_at: string;
  listings: Listing[];
  lowest_price_eur: number | null;
}

export interface PricePoint {
  scraped_at: string;
  price_eur: number | null;
  in_stock: boolean | null;
  ships_to_germany: boolean | null;
  source_id: string;
  source_name: string;
  listing_id: string;
}

export interface PriceSummary {
  listing_id: string;
  product_id: string;
  source_id: string;
  source_name: string;
  current_price_eur: number | null;
  min_price_eur: number | null;
  max_price_eur: number | null;
  price_7d_ago: number | null;
  change_pct: number | null;
  is_available: boolean | null;
  last_checked: string | null;
  is_all_time_low: boolean;
}

export interface Discovery {
  id: string;
  scope_id: string;
  name: string;
  brand: string | null;
  model: string | null;
  specs: Record<string, unknown>;
  source_name: string | null;
  source_url: string | null;
  price_eur: number | null;
  in_stock: boolean | null;
  ships_to_germany: boolean | null;
  screenshot_path: string | null;
  ai_reasoning: string | null;
  status: string;
  found_at: string;
}

export interface ResearchWatch {
  id: string;
  signal_id: string;
  watch_type: string;
  title: string;
  description: string | null;
  target_url: string | null;
  search_query: string | null;
  check_by_date: string | null;
  last_checked_at: string | null;
  status: string;
  result: string | null;
  created_at: string;
}

export interface ResearchSignal {
  id: string;
  discovered_at: string;
  run_id: string | null;
  signal_type: string;
  significance: string;
  title: string;
  summary: string | null;
  source_platform: string | null;
  source_url: string | null;
  source_author: string | null;
  product_id: string | null;
  scope_slug: string | null;
  action_required: boolean;
  action_description: string | null;
  follow_up_date: string | null;
  status: string;
  notes: string | null;
  watches: ResearchWatch[];
}

export interface AgentRun {
  id: string;
  run_type: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  scopes_checked: string[];
  products_checked: number;
  prices_updated: number;
  price_changes: Array<{
    direction: string;
    title: string;
    old_price: number;
    new_price: number;
    change_pct: number;
  }>;
  discoveries_found: number;
  errors: unknown[];
  data_checks: DataCheck[];
  tokens_used: Record<string, unknown>;
}

export interface DataCheck {
  // shared
  type?: string;
  check_type?: string;
  listing_id?: string;
  signal_id?: string;
  watch_id?: string;
  product_name?: string;
  source?: string;
  source_slug?: string;
  url?: string;
  status?: string;
  notes?: string;
  // price change / availability checks
  previous_in_stock?: boolean | null;
  previous_price_eur?: number | null;
  current_in_stock?: boolean | null;
  current_price_eur?: number | null;
  days_since_verified?: number | null;
  // cross-source outlier checks
  price_eur?: number | null;
  median_price?: number | null;
  deviation_pct?: number | null;
  direction?: string;
}

// ── API functions ──────────────────────────────────────────────────────────

export const api = {
  scopes: {
    list: () => apiFetch<Scope[]>("/scopes/"),
    create: (data: Partial<Scope>) =>
      apiFetch<Scope>("/scopes/", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Scope>) =>
      apiFetch<Scope>(`/scopes/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
    delete: (id: string) =>
      apiFetch<void>(`/scopes/${id}`, { method: "DELETE" }),
    // Scope-source management
    listSources: (scopeId: string) =>
      apiFetch<ScopeSource[]>(`/scopes/${scopeId}/sources`),
    linkSource: (scopeId: string, sourceId: string, template?: string) =>
      apiFetch<ScopeSource>(`/scopes/${scopeId}/sources`, {
        method: "POST",
        body: JSON.stringify({ source_id: sourceId, search_url_template: template }),
      }),
    unlinkSource: (scopeId: string, sourceId: string) =>
      apiFetch<void>(`/scopes/${scopeId}/sources/${sourceId}`, { method: "DELETE" }),
  },

  sources: {
    list: () => apiFetch<Source[]>("/sources/"),
    health: () => apiFetch<SourceHealth[]>("/sources/health"),
    create: (data: Partial<Source>) =>
      apiFetch<Source>("/sources/", { method: "POST", body: JSON.stringify(data) }),
    toggle: (id: string) =>
      apiFetch<Source>(`/sources/${id}/toggle`, { method: "PATCH" }),
    delete: (id: string) =>
      apiFetch<void>(`/sources/${id}`, { method: "DELETE" }),
  },

  products: {
    list: (scopeId?: string) =>
      apiFetch<Product[]>(`/products/${scopeId ? `?scope_id=${scopeId}` : ""}`),
    get: (id: string) => apiFetch<Product>(`/products/${id}`),
    create: (data: Partial<Product>) =>
      apiFetch<Product>("/products/", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Product>) =>
      apiFetch<Product>(`/products/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
    delete: (id: string) =>
      apiFetch<void>(`/products/${id}`, { method: "DELETE" }),
    addListing: (productId: string, data: { source_id: string; listing_url: string; listing_title?: string; is_primary?: boolean }) =>
      apiFetch<Listing>(`/products/${productId}/listings`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    deleteListing: (productId: string, listingId: string) =>
      apiFetch<void>(`/products/${productId}/listings/${listingId}`, { method: "DELETE" }),
  },

  prices: {
    forProduct: (productId: string, days = 30) =>
      apiFetch<PricePoint[]>(`/prices/product/${productId}?days=${days}`),
    summaryForProduct: (productId: string) =>
      apiFetch<PriceSummary[]>(`/prices/product/${productId}/summary`),
  },

  discoveries: {
    list: (status = "pending") =>
      apiFetch<Discovery[]>(`/discoveries/?status=${status}`),
    countPending: () =>
      apiFetch<{ count: number }>("/discoveries/count/pending"),
    review: (id: string, action: "approve" | "reject", notes?: string) =>
      apiFetch<Discovery>(`/discoveries/${id}/review`, {
        method: "POST",
        body: JSON.stringify({ action, notes }),
      }),
  },

  runs: {
    list: (limit = 20) => apiFetch<AgentRun[]>(`/runs/?limit=${limit}`),
    latest: () => apiFetch<AgentRun | null>("/runs/latest"),
    latestByType: async (type: string): Promise<AgentRun | null> => {
      const runs = await apiFetch<AgentRun[]>(`/runs/?limit=20`);
      return runs.find((r) => r.run_type === type) ?? null;
    },
  },

  research: {
    listSignals: (params?: { signal_type?: string; status?: string; limit?: number }) => {
      const q = new URLSearchParams();
      if (params?.signal_type) q.set("signal_type", params.signal_type);
      if (params?.status) q.set("status", params.status);
      if (params?.limit) q.set("limit", String(params.limit));
      const qs = q.toString();
      return apiFetch<ResearchSignal[]>(`/research/signals${qs ? `?${qs}` : ""}`);
    },
    createSignal: (data: Partial<ResearchSignal> & { watches?: Partial<ResearchWatch>[] }) =>
      apiFetch<ResearchSignal>("/research/signals", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    updateSignal: (id: string, data: Partial<ResearchSignal>) =>
      apiFetch<ResearchSignal>(`/research/signals/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    listWatches: (status?: string) =>
      apiFetch<ResearchWatch[]>(`/research/watches${status ? `?status=${status}` : ""}`),
    updateWatch: (id: string, data: Partial<ResearchWatch>) =>
      apiFetch<ResearchWatch>(`/research/watches/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
  },
};
