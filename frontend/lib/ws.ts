/**
 * WebSocket client for real-time dashboard updates.
 * Reconnects automatically on disconnect.
 */

type WsEvent = {
  type: "run_started" | "run_progress" | "run_completed" | "price_alert" | "new_discovery";
  data: Record<string, unknown>;
};

type Handler = (event: WsEvent) => void;

class PriceWatchSocket {
  private ws: WebSocket | null = null;
  private handlers: Handler[] = [];
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  connect() {
    if (typeof window === "undefined") return;
    if (this.ws?.readyState === WebSocket.OPEN) return;

    const websocketUrl =
      process.env.NEXT_PUBLIC_PRICEWATCH_WS_URL ?? "ws://127.0.0.1:8000/ws";
    this.ws = new WebSocket(websocketUrl);

    this.ws.onopen = () => {
      console.log("[PriceWatch WS] Connected");
      if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    };

    this.ws.onmessage = (evt) => {
      try {
        const event: WsEvent = JSON.parse(evt.data);
        this.handlers.forEach((h) => h(event));
      } catch (e) {
        console.error("[PriceWatch WS] Parse error", e);
      }
    };

    this.ws.onclose = () => {
      console.log("[PriceWatch WS] Disconnected — reconnecting in 5s");
      this.reconnectTimer = setTimeout(() => this.connect(), 5000);
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  subscribe(handler: Handler): () => void {
    this.handlers.push(handler);
    return () => {
      this.handlers = this.handlers.filter((h) => h !== handler);
    };
  }

  disconnect() {
    this.ws?.close();
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
  }
}

export const socket = new PriceWatchSocket();
