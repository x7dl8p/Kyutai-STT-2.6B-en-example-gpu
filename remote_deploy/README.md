# Remote deployment artifacts (Windows GPU box)

Everything actually run on `ali@192.168.1.20` (Windows, i3, 4GB RAM, GTX 1060 + RTX 2060),
pulled back here so it survives beyond that one machine. See
[`../DEPLOYMENT_CONTEXT.md`](../DEPLOYMENT_CONTEXT.md) for the full narrative — problems, root
causes, fixes — and [`../HOW_IT_WORKS.md`](../HOW_IT_WORKS.md) for the plain-English pipeline
explanation.

## Layout

- `launchers/run_s2s.bat` — starts the backend (Whisper on cuda:1, Qwen3-TTS on cuda:0). Reads
  `%GEMINI_API_KEY%` from the environment — **set it before running**, it is not embedded here.
- `launchers/run_proxy.bat` — single-port reverse proxy (serves UI + forwards the realtime
  WebSocket) on port 8080.
- `launchers/run_ngrok.bat` — HTTPS tunnel to the proxy.
- `launchers/run_demo.bat` — the demo UI, pointed at the ngrok hostname via `SPEECH_TO_SPEECH_URL`.
- `scripts/reshard.py` — splits a single huge `.safetensors` checkpoint into small shards.
  **Required** for Qwen3-TTS on this box: transformers memory-maps the whole checkpoint at load,
  and a single 3.83 GB mapping causes an access violation on 4 GB RAM. See
  `DEPLOYMENT_CONTEXT.md §5.12` for the full diagnosis.
- `scripts/proxy.py` — copy of `demo/proxy.py` as deployed (the only file actually added inside
  the cloned repo on the remote box; `git status` there shows no tracked-file changes).

## To redeploy on a fresh Windows box

1. Clone `huggingface/speech-to-speech`, `uv sync`, `uv pip install -e .[kokoro]` (optional).
2. Download STT/TTS models (`hf download openai/whisper-small`,
   `hf download Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`).
3. Run `python scripts/reshard.py` (edit the paths at the top first) to produce the sharded
   Qwen3-TTS checkpoint — only needed on RAM-constrained boxes; skip on 8GB+.
4. Copy `demo/proxy.py` from `scripts/proxy.py` into the cloned repo's `demo/` folder.
5. `set GEMINI_API_KEY=...` then run the four `launchers\*.bat` in order: s2s → proxy → ngrok →
   demo (read ngrok's hostname before starting demo, or hardcode it in `run_demo.bat` first).
