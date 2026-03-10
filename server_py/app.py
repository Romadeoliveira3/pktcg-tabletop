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


sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
)
http_app = FastAPI(title="PvP Tabletop Realtime")


def _room_size(room_id: str) -> int:
    namespace_rooms = sio.manager.rooms.get("/", {})
    room = namespace_rooms.get(room_id)
    return len(room) if room else 0


@http_app.get("/health-check")
async def health_check() -> JSONResponse:
    return JSONResponse({"status": "ready"})


@http_app.get("/api/health-check")
async def api_health_check() -> JSONResponse:
    return JSONResponse({"status": "ready"})


@http_app.get("/")
async def serve_index() -> FileResponse:
    if not INDEX_FILE.exists():
        raise HTTPException(status_code=503, detail="Frontend build not found")
    return FileResponse(INDEX_FILE)


@http_app.get("/{requested_path:path}", response_model=None)
async def serve_frontend(requested_path: str):
    if not INDEX_FILE.exists():
        raise HTTPException(status_code=503, detail="Frontend build not found")

    if requested_path:
        candidate = (BUILD_DIR / requested_path).resolve()
        if BUILD_DIR in candidate.parents and candidate.is_file():
            return FileResponse(candidate)

        if "." in Path(requested_path).name:
            raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(INDEX_FILE)


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


app = socketio.ASGIApp(sio, other_asgi_app=http_app, socketio_path="socket.io")
