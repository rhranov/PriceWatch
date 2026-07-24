"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronLeft } from "lucide-react";

const PAGE_NAMES: Record<string, string> = {
  "/products":    "Products",
  "/scopes":      "Scopes",
  "/sources":     "Sources",
  "/discoveries": "Discoveries",
  "/research":    "Research",
  "/history":     "History",
};

export function AppHeader() {
  const pathname = usePathname();
  if (pathname === "/") return null;

  const name = PAGE_NAMES[pathname] ?? "Page";

  return (
    <header className="flex items-center gap-2 px-4 sm:px-6 py-3 border-b border-border bg-card/60 backdrop-blur-sm shrink-0">
      <Link
        href="/"
        className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
      >
        <ChevronLeft className="w-3.5 h-3.5" />
        <div className="w-5 h-5 rounded bg-primary flex items-center justify-center shrink-0">
          <span className="text-primary-foreground text-[9px] font-bold">PW</span>
        </div>
      </Link>
      <span className="text-muted-foreground/40 text-sm">/</span>
      <span className="text-sm font-medium text-foreground">{name}</span>
    </header>
  );
}
