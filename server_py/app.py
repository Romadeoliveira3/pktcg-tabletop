from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import socketio
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse


BASE_DIR = Path(__file__).resolve().parent.parent
BUILD_DIR = BASE_DIR / "build"
INDEX_FILE = BUILD_DIR / "index.html"

GAME_EVENTS = (
    "chatMessage",
    "boardState",
    "deckLoaded",
    "boardReset",
    "cardsMoved",
    "slotsMoved",
    "cardsBenched",
    "activeBenched",
    "cardPromoted",
    "slotPromoted",
    "stadiumPlayed",
    "cardsEvolved",
    "cardsAttached",
    "damageUpdated",
    "markerUpdated",
    "pokemonToggle",
    "prizeToggle",
    "handToggle",
    "oppDamageUpdated",
)


from fastapi.middleware.cors import CORSMiddleware

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
)
http_app = FastAPI(title="Pokemon TCG Simulator Realtime")

http_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from fastapi.staticfiles import StaticFiles

def _room_size(room_id: str) -> int:
    namespace_rooms = sio.manager.rooms.get("/", {})
    room = namespace_rooms.get(room_id)
    return len(room) if room else 0


PREFIX = "/simulator/pktcg-simulator"


@http_app.get(f"{PREFIX}/health-check")
@http_app.get("/health-check") # Keep for docker healthcheck
async def health_check() -> JSONResponse:
    return JSONResponse({"status": "ready"})


@http_app.get(f"{PREFIX}/api/health-check")
async def api_health_check() -> JSONResponse:
    return JSONResponse({"status": "ready"})


@http_app.get(f"{PREFIX}/")
@http_app.get(f"{PREFIX}")
async def serve_index() -> FileResponse:
    if not INDEX_FILE.exists():
        raise HTTPException(status_code=503, detail="Frontend build not found")
    return FileResponse(INDEX_FILE)

# Monta arquivos estáticos do SvelteKit (Tudo que estiver em build/)
if BUILD_DIR.exists():
    http_app.mount(PREFIX, StaticFiles(directory=str(BUILD_DIR), html=True), name="simulator_static")

@http_app.get(PREFIX + "/{requested_path:path}", response_model=None)
async def serve_frontend(requested_path: str):
    # Se chegou aqui, o arquivo não existe em StaticFiles, então retornamos index.html (SPA)
    if INDEX_FILE.exists():
        return FileResponse(INDEX_FILE)
    raise HTTPException(status_code=404, detail="Not found")


@sio.event
async def connect(sid: str, environ: dict, auth: dict | None = None) -> None:
    return None


@sio.event
async def createRoom(sid: str) -> None:
    room_id = str(uuid4())
    await sio.enter_room(sid, room_id)
    await sio.emit("createdRoom", {"roomId": room_id}, to=sid)


@sio.event
async def joinRoom(sid: str, data: dict | None = None) -> None:
    room_id = (data or {}).get("roomId")
    if not room_id:
        return

    if _room_size(room_id) > 1:
        return

    await sio.enter_room(sid, room_id)
    await sio.emit("joinedRoom", {"roomId": room_id}, to=sid)
    await sio.emit("opponentJoined", room=room_id, skip_sid=sid)


@sio.event
async def leaveRoom(sid: str, data: dict | None = None) -> None:
    room_id = (data or {}).get("roomId")
    if not room_id:
        return

    await sio.leave_room(sid, room_id)
    await sio.emit("leftRoom", {"roomId": room_id}, to=sid)
    await sio.emit("opponentLeft", room=room_id, skip_sid=sid)


@sio.event
async def disconnect(sid: str) -> None:
    for room_id in sio.rooms(sid, namespace="/"):
        if room_id == sid:
            continue
        await sio.emit("opponentLeft", room=room_id, skip_sid=sid)


def _register_relay(event_name: str) -> None:
    @sio.on(event_name)
    async def relay(sid: str, data: dict | None = None, _event: str = event_name) -> None:
        payload = data or {}
        room_id = payload.get("room")
        if not room_id:
            return
        await sio.emit(_event, payload, room=room_id, skip_sid=sid)


for game_event in GAME_EVENTS:
    _register_relay(game_event)


app = socketio.ASGIApp(sio, other_asgi_app=http_app, socketio_path="/simulator/pktcg-simulator/socket.io")
