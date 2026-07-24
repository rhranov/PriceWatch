"use client";

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { socket } from "@/lib/ws";
import { toast } from "sonner";

export function WsProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();

  useEffect(() => {
    socket.connect();

    const unsub = socket.subscribe((event) => {
      switch (event.type) {
        case "run_started":
          qc.invalidateQueries({ queryKey: ["runs"] });
          toast.info("Daily pipeline started");
          break;
        case "run_completed":
          qc.invalidateQueries({ queryKey: ["runs"] });
          qc.invalidateQueries({ queryKey: ["products"] });
          qc.invalidateQueries({ queryKey: ["discoveries"] });
          qc.invalidateQueries({ queryKey: ["prices"] });
          if ((event.data as { status?: string }).status === "completed") {
            const discoveries = (event.data as { discoveries_found?: number }).discoveries_found ?? 0;
            toast.success(
              discoveries
                ? `Run complete · ${discoveries} new product(s) found!`
                : "Run complete"
            );
          } else {
            toast.error("Run failed — check History for details");
          }
          break;
        case "price_alert":
          qc.invalidateQueries({ queryKey: ["prices"] });
          const d = event.data as { product_name?: string; direction?: string; change_pct?: number };
          toast.info(`Price ${d.direction}: ${d.product_name} ${d.change_pct}%`);
          break;
        case "new_discovery":
          qc.invalidateQueries({ queryKey: ["discoveries"] });
          const disc = event.data as { name?: string };
          toast.success(`New product found: ${disc.name}`);
          break;
      }
    });

    return () => {
      unsub();
      socket.disconnect();
    };
  }, [qc]);

  return <>{children}</>;
}
