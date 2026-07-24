"use client";

import { Toaster as SonnerToaster } from "sonner";

export function Toaster() {
  return (
    <SonnerToaster
      theme="dark"
      position="bottom-right"
      toastOptions={{
        style: {
          background: "hsl(222, 20%, 11%)",
          border: "1px solid hsl(222, 20%, 18%)",
          color: "hsl(210, 20%, 92%)",
        },
      }}
    />
  );
}
