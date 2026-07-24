import type { Metadata } from "next";
import "./globals.css";
import { AppHeader } from "@/components/AppHeader";
import { Toaster } from "@/components/ui/Toaster";
import { QueryProvider } from "@/components/QueryProvider";
import { WsProvider } from "@/components/WsProvider";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "PriceWatch",
  description: "AI Hardware Price Tracker",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="flex flex-col h-screen overflow-hidden bg-background text-foreground">
        <QueryProvider>
          <WsProvider>
            <AppHeader />
            <main className="flex-1 overflow-auto">
              {children}
            </main>
            <Toaster />
          </WsProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
