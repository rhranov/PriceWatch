"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import {
  LayoutDashboard, Package, Sparkles, History,
  Layers, Globe, FlaskConical, X,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/",           label: "Dashboard",  icon: LayoutDashboard },
  { href: "/products",   label: "Products",   icon: Package },
  { href: "/scopes",     label: "Scopes",     icon: Layers },
  { href: "/sources",    label: "Sources",    icon: Globe },
  { href: "/discoveries",label: "Discoveries",icon: Sparkles },
  { href: "/research",   label: "Research",   icon: FlaskConical },
  { href: "/history",    label: "History",    icon: History },
];

interface Props {
  mobileOpen: boolean;
  onMobileClose: () => void;
}

export function Sidebar({ mobileOpen, onMobileClose }: Props) {
  const pathname = usePathname();

  const { data: pendingCount } = useQuery({
    queryKey: ["discoveries", "count"],
    queryFn: () => api.discoveries.countPending(),
    refetchInterval: 30_000,
  });

  return (
    <>
      {/* Backdrop — mobile only */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm md:hidden"
          onClick={onMobileClose}
        />
      )}

      {/* Sidebar panel */}
      <aside
        className={cn(
          // Positioning: fixed on mobile so it overlays; static on md+
          "fixed md:relative inset-y-0 left-0 z-50 md:z-auto",
          // Width: full drawer on mobile, icon-only on md, full on lg
          "w-64 md:w-14 lg:w-56",
          // Base styles
          "flex flex-col shrink-0 border-r border-border bg-card",
          // Slide transition
          "transition-transform duration-200 ease-in-out",
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        )}
      >
        {/* Logo row */}
        <div className="flex items-center gap-3 px-3 py-[18px] border-b border-border">
          <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center shrink-0">
            <span className="text-primary-foreground text-xs font-bold">PW</span>
          </div>
          {/* Label: visible on mobile drawer + lg sidebar */}
          <div className="flex-1 block md:hidden lg:block min-w-0">
            <p className="font-bold text-foreground text-sm leading-none truncate">PriceWatch</p>
            <p className="text-[11px] text-muted-foreground mt-0.5">Germany · EUR</p>
          </div>
          {/* Close button — mobile only */}
          <button
            onClick={onMobileClose}
            className="p-1 rounded-md text-muted-foreground hover:text-foreground md:hidden shrink-0"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Nav links */}
        <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            const badge = label === "Discoveries" && pendingCount?.count ? pendingCount.count : null;

            return (
              <Link
                key={href}
                href={href}
                title={label}
                onClick={onMobileClose}
                className={cn(
                  "relative flex items-center gap-3 px-2.5 py-2 rounded-lg text-sm transition-colors",
                  active
                    ? "bg-primary/10 text-primary font-medium"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted",
                )}
              >
                <Icon className="w-4 h-4 shrink-0" />

                {/* Label: mobile drawer + lg sidebar */}
                <span className="flex-1 block md:hidden lg:block truncate">{label}</span>

                {/* Badge when label is visible */}
                {badge != null && (
                  <>
                    <span className="block md:hidden lg:flex text-[10px] bg-yellow-500/20 text-yellow-400 rounded-full w-5 h-5 items-center justify-center font-bold shrink-0">
                      {badge > 9 ? "9+" : badge}
                    </span>
                    {/* Dot in icon-only mode */}
                    <span className="absolute top-1 right-1 hidden md:block lg:hidden w-2 h-2 rounded-full bg-yellow-400" />
                  </>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Footer — lg only */}
        <div className="hidden lg:block px-4 py-3 border-t border-border">
          <p className="text-xs text-muted-foreground">Daily check: 10:00 AM Berlin</p>
        </div>
      </aside>
    </>
  );
}
