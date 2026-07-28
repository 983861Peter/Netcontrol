# ws_broadcast.py
import asyncio
import json
from fastapi import WebSocket
# from collections import set

clients = set()

async def register(ws: WebSocket):
    clients.add(ws)

async def unregister(ws: WebSocket): 
    try:
        clients.discard(ws)
    except KeyError:
        pass

async def broadcast(payload: dict):
    txt = json.dumps(payload)
    to_remove = []
    for ws in list(clients):
        try:
            await ws.send_text(txt)
        except Exception:
            to_remove.append(ws)
    for ws in to_remove:
        try:
            clients.discard(ws)
        except Exception:
            pass

def broadcast_ws_event(payload: dict):
    # helper to be called synchronously from background threads by scheduling task:
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(broadcast(payload))
    except RuntimeError:
        # if not in event loop (called from thread), use asyncio.run_coroutine_threadsafe
        loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(broadcast(payload), loop)
