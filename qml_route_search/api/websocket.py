from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List
import json

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        # Maps route_id to list of active websocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, route_id: str):
        await websocket.accept()
        if route_id not in self.active_connections:
            self.active_connections[route_id] = []
        self.active_connections[route_id].append(websocket)

    def disconnect(self, websocket: WebSocket, route_id: str):
        if route_id in self.active_connections:
            self.active_connections[route_id].remove(websocket)
            if not self.active_connections[route_id]:
                del self.active_connections[route_id]

    async def broadcast_update(self, route_id: str, message: dict):
        if route_id in self.active_connections:
            for connection in self.active_connections[route_id]:
                await connection.send_json(message)

manager = ConnectionManager()

@router.websocket("/ws/route-updates/{route_id}")
async def websocket_endpoint(websocket: WebSocket, route_id: str):
    await manager.connect(websocket, route_id)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming client messages if any
    except WebSocketDisconnect:
        manager.disconnect(websocket, route_id)
