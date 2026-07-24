"use client";

import { useState, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  TrendingDown, Sparkles, Globe, Activity as ActivityIcon,
  Settings, Package, Layers, FlaskConical, History,
} from "lucide-react";
import { PricesTab } from "@/components/tabs/PricesTab";
import { DiscoveriesTab } from "@/components/tabs/DiscoveriesTab";
import { SourcesTab } from "@/components/tabs/SourcesTab";
import { ActivityTab } from "@/components/tabs/ActivityTab";

type TabId = "prices" | "discoveries" | "sources" | "activity";

const TABS: {
  id: TabId;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}[] = [
  { id: "prices",      label: "Prices",      icon: TrendingDown },
  { id: "discoveries", label: "Discoveries", icon: Sparkles },
  { id: "sources",     label: "Sources",     icon: Globe },
  { id: "activity",    label: "Activity",    icon: ActivityIcon },
];

const SETTINGS_NAV = [
  { href: "/products",   label: "Products",   icon: Package },
  { href: "/scopes",     label: "Scopes",     icon: Layers },
  { href: "/research",   label: "Research",   icon: FlaskConical },
  { href: "/history",    label: "History",    icon: History },
];

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<TabId>("prices");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onOutsideClick(e: MouseEvent) {
      if (settingsRef.current && !settingsRef.current.contains(e.target as Node)) {
        setSettingsOpen(false);
      }
    }
    document.addEventListener("mousedown", onOutsideClick);
    return () => document.removeEventListener("mousedown", onOutsideClick);
  }, []);

  const { data: pendingCount } = useQuery({
    queryKey: ["discoveries", "count"],
    queryFn: () => api.discoveries.countPending(),
    refetchInterval: 30_000,
  });

  const { data: healthData = [] } = useQuery({
    queryKey: ["sources-health"],
    queryFn: api.sources.health,
    refetchInterval: 60_000,
  });

  const { data: latestRun } = useQuery({
    queryKey: ["runs", "latest"],
    queryFn: () => api.runs.latest(),
    refetchInterval: 15_000,
  });

  const failingCount = healthData.filter((h) => h.status === "failing").length;
  const isRunning = latestRun?.status === "running";

  function tabIndicator(id: TabId): React.ReactNode {
    if (id === "discoveries" && pendingCount?.count) {
      return (
        <span className="ml-1 text-[10px] bg-yellow-500/20 text-yellow-400 rounded-full px-1.5 py-0.5 font-bold leading-none">
          {pendingCount.count > 9 ? "9+" : pendingCount.count}
        </span>
      );
    }
    if (id === "sources" && failingCount > 0) {
      return <span className="ml-1 w-1.5 h-1.5 rounded-full bg-red-400 inline-block" />;
    }
    if (id === "activity" && isRunning) {
      return <span className="ml-1 w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse inline-block" />;
    }
    return null;
  }

  return (
    <div className="flex flex-col h-full">
      {/* ── Sticky header ──────────────────────────────────────────────── */}
      <div className="sticky top-0 z-10 shrink-0 bg-background/95 backdrop-blur-sm border-b border-border">

        {/* Status strip */}
        <div className="flex items-center gap-2 px-4 sm:px-6 pt-2.5 pb-1 text-xs text-muted-foreground">
          {/* Logo mark */}
          <div className="w-5 h-5 rounded bg-primary flex items-center justify-center shrink-0">
            <span className="text-primary-foreground text-[9px] font-bold">PW</span>
          </div>
          <span className="font-semibold text-foreground">PriceWatch</span>
          <span className="opacity-30 hidden sm:inline">·</span>
          <span className="hidden sm:inline">AI Hardware · Germany</span>

          <div className="ml-auto flex items-center gap-3">
            {isRunning && (
              <span className="flex items-center gap-1.5 text-blue-400 font-medium">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                <span className="hidden sm:inline">Running</span>
              </span>
            )}
            <span className="flex items-center gap-1.5 text-green-400/80">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              <span className="hidden sm:inline">Live</span>
            </span>

            {/* Settings dropdown */}
            <div ref={settingsRef} className="relative">
              <button
                onClick={() => setSettingsOpen((v) => !v)}
                className={cn(
                  "p-1.5 rounded-md transition-colors",
                  settingsOpen
                    ? "bg-muted text-foreground"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted",
                )}
                title="More pages"
              >
                <Settings className="w-3.5 h-3.5" />
              </button>

              {settingsOpen && (
                <div className="absolute right-0 top-full mt-1.5 w-44 rounded-xl border border-border bg-card shadow-xl z-50 overflow-hidden">
                  <div className="px-3 py-2 border-b border-border">
                    <p className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider">
                      Management
                    </p>
                  </div>
                  {SETTINGS_NAV.map(({ href, label, icon: Icon }) => (
                    <Link
                      key={href}
                      href={href}
                      onClick={() => setSettingsOpen(false)}
                      className="flex items-center gap-2.5 px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                    >
                      <Icon className="w-3.5 h-3.5 shrink-0" />
                      {label}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Tab bar */}
        <div className="flex px-2 sm:px-4 gap-0.5">
          {TABS.map(({ id, label, icon: Icon }) => {
            const active = activeTab === id;
            return (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className={cn(
                  "flex items-center justify-center gap-1.5",
                  // On mobile: equal flex columns; on sm+: natural width with padding
                  "flex-1 sm:flex-none sm:px-5",
                  "py-3 text-sm font-medium transition-colors",
                  "border-b-2 -mb-px",
                  active
                    ? "border-primary text-primary"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:border-border",
                )}
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span className="hidden sm:inline">{label}</span>
                {tabIndicator(id)}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Tab content ────────────────────────────────────────────────── */}
      {/* key forces remount → triggers dash-tab-in animation on switch */}
      <div key={activeTab} className="flex-1 overflow-auto p-4 sm:p-6 dash-tab-in">
        {activeTab === "prices"      && <PricesTab />}
        {activeTab === "discoveries" && <DiscoveriesTab />}
        {activeTab === "sources"     && <SourcesTab />}
        {activeTab === "activity"    && <ActivityTab />}
      </div>
    </div>
  );
}
