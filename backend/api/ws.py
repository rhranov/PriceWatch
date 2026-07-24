"""
WebSocket endpoint for real-time dashboard updates.
Clients connect to /ws and receive JSON events as agent runs progress.
"""

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from backend.config import settings

router = APIRouter()
MAX_CONNECTIONS = 20

# In-memory connection manager
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        origin = ws.headers.get("origin")
        if origin != settings.frontend_url:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return False
        if len(self.active) >= MAX_CONNECTIONS:
            await ws.close(code=status.WS_1013_TRY_AGAIN_LATER)
            return False
        await ws.accept()
        self.active.append(ws)
        return True

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, event_type: str, data: Any):
        message = json.dumps({"type": event_type, "data": data})
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    if not await manager.connect(websocket):
        return
    try:
        while True:
            await asyncio.wait_for(websocket.receive_text(), timeout=45)
    except (WebSocketDisconnect, asyncio.TimeoutError):
        await websocket.close()
    finally:
        manager.disconnect(websocket)


async def broadcast_event(event_type: str, data: Any):
    """
    Call this from anywhere in the backend to push a live update to all
    connected dashboard clients.

    Event types:
      - run_started     → {run_id, run_type, started_at}
      - run_progress    → {run_id, message, products_checked, prices_updated}
      - run_completed   → {run_id, status, discoveries_found, price_changes}
      - price_alert     → {product_name, source, old_price, new_price, change_pct}
      - new_discovery   → {discovery_id, name, scope, price_eur, source}
    """
    await manager.broadcast(event_type, data)
