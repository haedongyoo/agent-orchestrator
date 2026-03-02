"""
Web Chat Connector — WebSocket endpoint for real-time thread updates.

Events pushed to client:
  - new_message
  - task_status
  - approval_requested
  - approval_decided
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict
import uuid
import json

router = APIRouter()

# In-memory connection registry: thread_id → set of websockets
# MVP only — replace with Redis pub/sub for multi-worker deployments
_connections: Dict[str, set[WebSocket]] = {}


@router.websocket("/threads/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: uuid.UUID):
    await websocket.accept()
    key = str(thread_id)
    _connections.setdefault(key, set()).add(websocket)

    try:
        while True:
            # Client can send typing indicators or keep-alives
            data = await websocket.receive_text()
            # TODO: handle client→server events if needed
    except WebSocketDisconnect:
        _connections.get(key, set()).discard(websocket)


async def broadcast(thread_id: uuid.UUID, event: dict) -> None:
    """Push an event to all connected WebSocket clients for a thread."""
    key = str(thread_id)
    dead = set()
    for ws in _connections.get(key, set()):
        try:
            await ws.send_text(json.dumps(event))
        except Exception:
            dead.add(ws)
    _connections[key] = _connections.get(key, set()) - dead
