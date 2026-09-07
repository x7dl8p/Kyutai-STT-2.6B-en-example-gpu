# live-transcribe

Minimal live transcription. A blob in the browser bounces with your voice
volume; the text you speak appears under it, streamed word-by-word.

- **Model:** [`kyutai/stt-1b-en_fr`](https://huggingface.co/kyutai/stt-1b-en_fr)
  by default (fits a 4 GB card, ~3x real time, ~0.5 s inherent delay).
  Set `STT_HF_REPO=kyutai/stt-2.6b-en` for best accuracy — needs ~8 GB VRAM
  and trails your voice by ~2.5 s.
- Loaded once on the GPU (bf16) and warmed up at startup.
- **No VAD, no turn detection.** Audio flows straight into the model frame by
  frame. Kyutai STT is a *delayed-streaming* model, so text always trails the
  audio by a fixed amount.
- **Blob bounce** is computed client-side from a Web Audio `AnalyserNode` —
  no server round-trip, so it tracks volume instantly.
- The browser captures the mic, resamples to 24 kHz in an `AudioWorklet`, and
  streams 16-bit PCM frames over one WebSocket. One listener at a time.

## Setup (once)

```bash
./setup.sh                       # builds .venv/ and installs requirements.txt
```

or by hand:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
source .venv/bin/activate
python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Then open http://localhost:8000 and click once to grant mic access.
Watch startup — it prints `[stt] ready on <gpu> (x.x/4.0 GB VRAM)` once the
model is loaded and warm.

### Config (env vars, set before the run command)

| var           | default              | note |
|---------------|----------------------|------|
| `STT_HF_REPO` | `kyutai/stt-1b-en_fr` | `kyutai/stt-2.6b-en` for best accuracy (~8 GB VRAM) |
| `STT_DEVICE`  | `cuda`               | `cpu` runs but is ~0.08x real time — unusable for live |
| `HOST`/`PORT` | `0.0.0.0` / `8000`   | passed on the uvicorn command line above |

```bash
STT_HF_REPO=kyutai/stt-2.6b-en python -m uvicorn server:app --port 8000
```

The server exits early with a clear message if `STT_DEVICE=cuda` but no CUDA
device is visible to the process.

## GPU inside this Incus container

This container only had `nvidia-smi` + NVML forwarded from the host, not the
CUDA driver libraries, so `torch.cuda.is_available()` was `False`. What fixed it
(host driver **580.173.02**, matched exactly):

1. Push the host's driver userspace libs in (run on the laptop host):
   ```bash
   incus exec projects -- mkdir -p /root/cuda-libs
   for f in /usr/lib/x86_64-linux-gnu/libcuda.so.580.173.02 \
            /usr/lib/x86_64-linux-gnu/libnvidia-*.so.580.173.02; do
     incus file push "$f" projects/root/cuda-libs/
   done
   ```
2. Install them + SONAME symlinks (in the container):
   ```bash
   cp /root/cuda-libs/*.so.580.173.02 /usr/lib/x86_64-linux-gnu/
   cd /usr/lib/x86_64-linux-gnu
   ln -sfn libcuda.so.580.173.02 libcuda.so.1 && ln -sfn libcuda.so.1 libcuda.so
   ln -sfn libnvidia-ptxjitcompiler.so.580.173.02 libnvidia-ptxjitcompiler.so.1
   ln -sfn libnvidia-nvvm.so.580.173.02 libnvidia-nvvm.so.4
   ldconfig
   ```
3. Toolchain for `torch.compile` (moshi uses it): `apt install gcc libc6-dev libpython3.12-dev`

The cleaner alternative is `incus config set projects nvidia.runtime true` on the
host (needs `nvidia-container-toolkit`), which forwards all of this automatically
and survives host driver upgrades. The manual copy must be redone if the host
driver version changes.

## Files

- `setup.sh` — one-time venv build.
- `server.py` — FastAPI + WebSocket, model load / warmup / streaming loop.
- `static/index.html` — the whole UI: blob, live text, mic capture worklet.
