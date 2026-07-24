"use client";

import { Menu } from "lucide-react";

interface Props {
  onMenuClick: () => void;
}

export function MobileHeader({ onMenuClick }: Props) {
  return (
    <header className="flex md:hidden items-center gap-3 px-4 py-3 border-b border-border bg-card shrink-0">
      <button
        onClick={onMenuClick}
        className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        aria-label="Open navigation"
      >
        <Menu className="w-5 h-5" />
      </button>
      <div className="flex items-center gap-2">
        <div className="w-6 h-6 rounded-md bg-primary flex items-center justify-center">
          <span className="text-primary-foreground text-[10px] font-bold">PW</span>
        </div>
        <span className="font-bold text-sm text-foreground">PriceWatch</span>
      </div>
      <div className="ml-auto flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
        <span className="text-xs text-muted-foreground">Live</span>
      </div>
    </header>
  );
}
