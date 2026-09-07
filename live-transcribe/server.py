"""Live transcription server — Kyutai STT (delayed streaming, no VAD).

Loads a Kyutai STT model once on the GPU, warms it up, then streams text
token-by-token to the browser as raw 24 kHz PCM arrives over a WebSocket.

    STT_HF_REPO   HF repo to load    (default: kyutai/stt-1b-en_fr; fits a 4 GB
                                      card at ~3x real time. Use kyutai/stt-2.6b-en
                                      for best accuracy — needs ~8 GB VRAM.)
    STT_DEVICE    torch device       (default: cuda)
    HOST / PORT   bind address       (default: 0.0.0.0 / 8000)
"""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import torch
import moshi.models
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

HF_REPO = os.environ.get("STT_HF_REPO", "kyutai/stt-1b-en_fr")
DEVICE = os.environ.get("STT_DEVICE", "cuda")
STATIC = Path(__file__).parent / "static"

if DEVICE.startswith("cuda") and not torch.cuda.is_available():
    raise SystemExit(
        "STT_DEVICE=cuda but torch.cuda.is_available() is False.\n"
        "  - check `nvidia-smi` works in this shell\n"
        "  - check this venv's torch is a CUDA build:\n"
        "      python -c \"import torch; print(torch.__version__, torch.version.cuda)\"\n"
        "  - if in a container, make sure the GPU is passed through\n"
        "  - or set STT_DEVICE=cpu to run without a GPU (not real time)"
    )

# Mimi is always 24 kHz with an 1920-sample (80 ms) frame. The browser resamples
# to this rate before sending, so the wire format is fixed.
SAMPLE_RATE = 24000

torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True


class STT:
    def __init__(self) -> None:
        print(f"[stt] loading {HF_REPO} on {DEVICE} ...", flush=True)
        info = moshi.models.loaders.CheckpointInfo.from_hf_repo(HF_REPO)
        self.mimi = info.get_mimi(device=DEVICE)
        self.tokenizer = info.get_text_tokenizer()
        lm = info.get_moshi(device=DEVICE, dtype=torch.bfloat16)
        self.lm_gen = moshi.models.LMGen(lm, temp=0, temp_text=0.0)
        self.frame_size = self.mimi.frame_size
        assert int(self.mimi.sample_rate) == SAMPLE_RATE
        self._warmup()
        if DEVICE.startswith("cuda"):
            free, total = torch.cuda.mem_get_info()
            print(
                f"[stt] ready on {torch.cuda.get_device_name(0)} "
                f"({(total - free) / 1e9:.1f}/{total / 1e9:.1f} GB VRAM)",
                flush=True,
            )
        else:
            print("[stt] ready on cpu", flush=True)

    @torch.inference_mode()
    def _warmup(self) -> None:
        silence = torch.zeros(
            (1, 1, self.frame_size), dtype=torch.float32, device=DEVICE
        )
        with self.mimi.streaming(1), self.lm_gen.streaming(1):
            for _ in range(16):
                self.lm_gen.step(self.mimi.encode(silence))

    def new_session(self) -> "Session":
        return Session(self)


class Session:
    """One WebSocket's streaming state. All calls run on a single worker thread."""

    def __init__(self, stt: STT) -> None:
        self.stt = stt
        self._mimi_cm = stt.mimi.streaming(1)
        self._lm_cm = stt.lm_gen.streaming(1)
        self._mimi_cm.__enter__()
        self._lm_cm.__enter__()

    @torch.inference_mode()
    def step(self, frame_bytes: bytes) -> str:
        pcm = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        chunk = torch.from_numpy(pcm).to(DEVICE).view(1, 1, -1)
        audio_tokens = self.stt.mimi.encode(chunk)
        text_tokens = self.stt.lm_gen.step(audio_tokens)
        if text_tokens is None:
            return ""
        token = text_tokens[0, 0, 0].item()
        if token in (0, 3):  # 0 = end-of-padding marker, 3 = padding
            return ""
        return self.stt.tokenizer.id_to_piece(token).replace("▁", " ")

    def close(self) -> None:
        self._lm_cm.__exit__(None, None, None)
        self._mimi_cm.__exit__(None, None, None)


app = FastAPI()
stt: STT | None = None
stt_lock = asyncio.Lock()


@app.on_event("startup")
def _load() -> None:
    global stt
    stt = STT()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    if stt_lock.locked():
        await websocket.send_json({"type": "busy"})
        await websocket.close()
        return

    async with stt_lock:
        loop = asyncio.get_running_loop()
        pool = ThreadPoolExecutor(max_workers=1)
        session = await loop.run_in_executor(pool, stt.new_session)
        frame_bytes = stt.frame_size * 2
        buf = bytearray()
        await websocket.send_json({"type": "ready", "sample_rate": SAMPLE_RATE})
        try:
            while True:
                buf.extend(await websocket.receive_bytes())
                pieces = []
                while len(buf) >= frame_bytes:
                    frame = bytes(buf[:frame_bytes])
                    del buf[:frame_bytes]
                    piece = await loop.run_in_executor(pool, session.step, frame)
                    if piece:
                        pieces.append(piece)
                if pieces:
                    await websocket.send_json({"type": "text", "text": "".join(pieces)})
        except WebSocketDisconnect:
            pass
        finally:
            await loop.run_in_executor(pool, session.close)
            pool.shutdown(wait=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
    )
