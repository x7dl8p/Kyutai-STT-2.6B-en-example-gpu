"""Single-port reverse proxy: demo UI (7860) + /v1/realtime WS -> backend (8765)."""
import asyncio
import httpx
import websockets
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import StreamingResponse

UI = "http://127.0.0.1:7860"
WS = "ws://127.0.0.1:8765"

app = FastAPI()
client = httpx.AsyncClient(base_url=UI, timeout=None)


@app.websocket("/v1/realtime")
async def realtime(ws: WebSocket):
    raw = ws.headers.get("sec-websocket-protocol")
    subs = [s.strip() for s in raw.split(",")] if raw else None

    up = None
    try:
        up = await websockets.connect(
            f"{WS}/v1/realtime",
            subprotocols=subs,
            max_size=None,
            ping_interval=None,
            open_timeout=20,
        )
    except Exception:
        await ws.close(code=1011)
        return

    chosen = up.subprotocol if up.subprotocol else (subs[0] if subs else None)
    await ws.accept(subprotocol=chosen)

    async def c2s():
        try:
            while True:
                m = await ws.receive()
                if m["type"] == "websocket.disconnect":
                    break
                if m.get("text") is not None:
                    await up.send(m["text"])
                elif m.get("bytes") is not None:
                    await up.send(m["bytes"])
        except Exception:
            pass

    async def s2c():
        try:
            async for m in up:
                if isinstance(m, bytes):
                    await ws.send_bytes(m)
                else:
                    await ws.send_text(m)
        except Exception:
            pass

    t1 = asyncio.create_task(c2s())
    t2 = asyncio.create_task(s2c())
    try:
        _, pending = await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
    finally:
        try:
            await up.close()
        except Exception:
            pass
        try:
            await ws.close()
        except Exception:
            pass


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy(path: str, request: Request):
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "content-length")}
    body = await request.body()
    req = client.build_request(request.method, "/" + path, headers=headers,
                               content=body, params=request.query_params)
    r = await client.send(req, stream=True)
    out = {k: v for k, v in r.headers.items()
           if k.lower() not in ("content-encoding", "content-length",
                                "transfer-encoding", "connection")}
    return StreamingResponse(r.aiter_raw(), status_code=r.status_code, headers=out)
