# speech-to-speech — Windows Deployment Context

Full record of deploying `huggingface/speech-to-speech` on a remote Windows machine,
including every failure encountered, its root cause, and the fix.

Last updated: 2026-09-01 · Status: **WORKING**

---

## 1. Target machine

| Item | Value |
|---|---|
| Host | `DESKTOP-514CSMM` @ `192.168.1.20` (Wi-Fi; Ethernet disconnected) |
| SSH | `ssh ali@192.168.1.20` — password auth |
| OS | Windows, shell is **`cmd.exe`** (not PowerShell — matters for env-var syntax) |
| CPU | Intel **i3-6100T** (Skylake, 2016) — dual core, **no AVX-512, no AMX** |
| RAM | **4 GB total** ← the single biggest constraint in this whole deployment |
| GPU | **NVIDIA RTX 2060**, 6 GB, driver 560.94 / CUDA 12.6 — currently **unused** |
| Repo | `C:\Users\ali\speech-to-speech` (clean clone, `main` @ `3986f45`) |
| Tailscale | `100.87.187.25` |

---

## 2. Final working configuration

**GPU build (current).** Both GPUs were idle for the whole first deployment; everything ran on a
2016 dual-core i3. Moving STT and TTS onto CUDA is what fixed the "slow to transcribe / robotic
voice / bad latency" complaints.

| Stage | Backend | Device | Why |
|---|---|---|---|
| VAD | Silero v5 + Smart Turn v3.2 | CPU (onnx) | tiny; not the bottleneck |
| **STT** | **`openai/whisper-small`**, `float16` | **cuda:1** (GTX 1060) | **217 ms** per 5 s of audio. Was whisper-tiny on CPU (seconds). RTX 2060 does it in 77 ms, but Qwen3 needs that card's VRAM |
| **LLM** | `gemini-3.5-flash-lite`, `reasoning_effort minimal` | API | gemma-4-31b-it cannot disable thinking; emitted `<thought>` blocks that TTS read aloud |
| **TTS** | **Qwen3-TTS 1.7B CustomVoice**, `float16`, `sdpa`, torch backend, **re-sharded checkpoint** | **cuda:0** (RTX 2060) | natural voice (replaces robotic MMS). TTFA **~700 ms**, RTF 0.73, peak **4.57 GB** VRAM |
| Streaming | `--stream_batch_sentences 1`, `--qwen3_tts_streaming_chunk_size 10` | — | chunk 10 measured best: TTFA 699 ms @ RTF 0.73 (see sweep in §5.12) |

**Measured TTS sweep** (RTX 2060, fp16, sdpa) — chunk size is the dominant latency knob:

| chunk | TTFA | RTF |
|---|---|---|
| 5 | 472 ms | 0.99 (too close to underrun) |
| **10** | **699 ms** | **0.73** ← chosen |
| 25 | 1445 ms | 0.87 |
| 50 | 3047 ms | 0.95 |

> **GPU split is deliberate.** Qwen3-TTS peaks at 4.57 GB of the RTX 2060's 6 GB. Putting Whisper
> on the same card would leave ~1 GB and risk a mid-conversation OOM. STT at 217 ms on the 1060 is
> far below the ~700 ms TTS TTFA, so it is not the critical path. Set
> `CUDA_DEVICE_ORDER=FASTEST_FIRST` so `cuda:0` is deterministically the RTX 2060.

---

## 3. Run commands (cmd.exe syntax)

> `set VAR=value` — **not** `$env:VAR="..."`. PowerShell syntax silently does nothing in cmd,
> which caused hours of "why is the UI asking for a URL".

### Terminal 1 — Backend (start first, wait ~40 s for `Uvicorn running`)
```cmd
cd /d C:\Users\ali\speech-to-speech
set HF_HOME=C:\Users\Ali\.cache\huggingface
set HF_HUB_DISABLE_XET=1
set CUDA_DEVICE_ORDER=FASTEST_FIRST
set FOR_DISABLE_CONSOLE_CTRL_HANDLER=1
.venv\Scripts\speech-to-speech.exe serve --host 0.0.0.0 --llm_backend chat-completions --model_name "gemini-3.5-flash-lite" --responses_api_base_url "https://generativelanguage.googleapis.com/v1beta/openai/" --responses_api_api_key "<GEMINI_API_KEY>" --responses_api_reasoning_effort minimal --responses_api_stream --stream_batch_sentences 1 --enable_live_transcription --stt whisper --stt_model_name openai/whisper-small --stt_device cuda:1 --stt_torch_dtype float16 --tts qwen3 --qwen3_tts_model_name "C:\Users\ali\models\Qwen3-TTS-1.7B-CustomVoice-sharded" --qwen3_tts_device cuda --qwen3_tts_dtype float16 --qwen3_tts_backend torch --qwen3_tts_attn_implementation sdpa --qwen3_tts_streaming_chunk_size 10 --no_qwen3_tts_non_streaming_mode
```

Healthy startup log ends with:
```
Qwen3-TTS model loaded
Using Qwen3-TTS streaming chunk size 10 (~800ms audio per chunk) on faster_qwen3_tts
CUDA graphs captured and ready
Qwen3TTSHandler warmed up
INFO:     Uvicorn running on http://0.0.0.0:8765
```

Confirm both GPUs are actually in use once a conversation is running:
```cmd
nvidia-smi
```
Expect python.exe resident on **both** cards (~4.6 GB on the RTX 2060, ~0.7 GB on the GTX 1060).

### Terminal 2 — Proxy (only needed for HTTPS / remote access)
```cmd
cd /d C:\Users\ali\speech-to-speech\demo
set FOR_DISABLE_CONSOLE_CTRL_HANDLER=1
.venv\Scripts\python.exe -m uvicorn --app-dir . proxy:app --host 0.0.0.0 --port 8080
```

### Terminal 3 — ngrok (only for HTTPS / remote access)
```cmd
C:\Users\ali\ngrokbin\ngrok.exe http 8080
```

### Terminal 4 — Demo UI (start LAST, after reading ngrok's hostname)
```cmd
cd /d C:\Users\ali\speech-to-speech\demo
set SPEECH_TO_SPEECH_URL=wss://<NGROK-HOST>/v1/realtime
.venv\Scripts\python.exe -m uvicorn --app-dir . server:app --host 0.0.0.0 --port 7860
```

**Order:** 1 → 2 → 3 → read ngrok URL → 4.

**Local-only testing** (simpler, ~100 MB less RAM): skip Terminals 2 & 3, and set
`set SPEECH_TO_SPEECH_URL=ws://localhost:8765/v1/realtime`, then open `http://localhost:7860`.

### Verify the env var actually applied
```cmd
curl -s http://localhost:7860/api/config
```
`s2sUrl` must contain your URL. If it shows `""`, the `set` did not apply and the UI will prompt for it.

---

## 4. Ports

| Port | Service |
|---|---|
| 8765 | Backend (OpenAI Realtime WS) |
| 7860 | Demo UI |
| 8080 | Reverse proxy (UI + WS on one origin) |
| 4040 | ngrok local dashboard |

---

## 5. Problems hit, and root causes

### 5.1 Gemini rejects `chat_template_kwargs`
`400 Unknown name "chat_template_kwargs"`. The pipeline injects this for any non-OpenAI base URL
(`base_openai_compatible_language_model.py`, `_build_extra_body`). It kills the server at **warmup**,
which fires one real API call before serving.
**Fix:** `--responses_api_disable_thinking False`, or supply `--responses_api_reasoning_effort` (takes precedence).

### 5.2 gemma-4-31b-it speaks its own reasoning
Emits `<thought>…</thought>` into visible content; TTS reads it aloud. With a small token budget the
entire allowance is consumed thinking → `output_tokens=0`, `audio=0.00s`.
Both suppression paths are rejected by the API:
- `chat_template_kwargs` → `400 Unknown name`
- `reasoning_effort` → `400 Thinking budget is not supported for this model`

**Fix:** switch to a Gemini model. `gemini-3.5-flash-lite` + `reasoning_effort minimal` → clean output.
(`none` is rejected on that model; `minimal` is the floor and matches the AI Studio dropdown.)

### 5.3 HF Xet transfers stall at 0 bytes
Downloads hang with zero-byte `.incomplete` blobs. Same file pulled at 22 MB/s with Xet off.
**Fix:** `set HF_HUB_DISABLE_XET=1`. Also set `HF_TOKEN` to avoid rate limits.

### 5.4 Qwen3-TTS is not usable on this machine
Two backends, both ruled out:
- **GGML** — `qwentts-cpp-python` publishes **only manylinux wheels**. No Windows build exists on any version.
  (On Linux its CPU wheel additionally requires **Intel AMX**, which is Xeon Sapphire Rapids 2023+ only —
  no consumer i3/i5/i7/i9 has it. Not relevant on Windows since the package isn't installed there at all.)
- **torch** — hard-refuses CPU: `ValueError: CUDA graphs require CUDA device`. On CUDA it needs the
  3.66 GB model resident first → `OSError: paging file is too small (os error 1455)` on a 4 GB box.

**Fix:** `--tts facebookMMS` — built in, ~139 MB, no native deps. Quality is robotic but it runs.

### 5.5 torch version mismatch → `torch_cpu.dll` / `c10.dll` access violations
`uv sync` resolves **torch 2.11.0**. Installing `2.6.0+cu124` from the PyTorch CUDA index (the first
CUDA build found) breaks binary compatibility with `numpy 2.4.3` / `transformers 5.16.1` →
`Exception code 0xc0000005` with no Python traceback.
**Fix:** `torch==2.11.0` from the **cu126** index (matches driver's CUDA 12.6):
```cmd
uv pip install --python .venv\Scripts\python.exe --reinstall torch==2.11.0 torchaudio --index-url https://download.pytorch.org/whl/cu126
```
Verified: `torch 2.11.0+cu126`, `cuda available: True`, sees the RTX 2060.

### 5.6 `whisper-tiny.en` rejects the language argument
`ValueError: Cannot specify task or language for an English-only model`. The `.en` checkpoints refuse
the `--language` parameter the pipeline always sends.
**Fix:** use multilingual `openai/whisper-tiny` (same size).

### 5.7 Silent backend deaths — `STATUS_CONTROL_C_EXIT`
No traceback, no crash event, RAM fine. Exit code `-1073741510` (`0xC000013A`).
Two contributing causes:
1. **Intel Fortran runtime** (via MKL/scipy) installs a console handler that aborts the process on any
   console-close event → `forrtl: error (200): program aborting due to window-CLOSE event`.
   **Fix:** `set FOR_DISABLE_CONSOLE_CTRL_HANDLER=1`
2. **SSH sessions.** Every SSH connect/disconnect destroys a console and broadcasts the event.
   Background polling loops running every 10–15 s were killing the backend repeatedly.
   **Fix:** don't poll while it loads. Scheduled tasks must be **S4U**, not "Interactive only" —
   the latter attaches a console and is just as vulnerable.

### 5.8 Windows OpenSSH job objects kill detached children
`Start-Process` / `&` backgrounding dies when the SSH channel closes — sshd puts each session in a Job
Object with kill-on-close. Task Scheduler with S4U logon avoids it entirely.

### 5.9 ngrok
- winget ships **3.3.1**; account minimum is **3.20.0** → `ERR_NGROK_121`. Self-update deletes the binary
  without replacing it. Download fresh from `https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip`.
- **Windows Defender quarantines ngrok.exe** seconds after download (confirmed: repeated detections,
  same threat ID). Requires an exclusion:
  `Add-MpPreference -ExclusionPath "C:\Users\ali\ngrokbin"` ← **remove this when done**.
- Free tier gives **one** domain. Two tunnels collide on the same hostname — this is why the reverse
  proxy exists.

### 5.10 `[object Event]` in the browser
The WebSocket failing. Two causes, both seen:
1. The demo hands the browser `SPEECH_TO_SPEECH_URL` verbatim and the browser connects **directly** —
   `localhost` means the *visitor's* machine, and an HTTPS page cannot open plain `ws://` (mixed content).
2. **Subprotocol negotiation.** The OpenAI Agents SDK sends `Sec-WebSocket-Protocol`; accepting with
   `subprotocol=None` makes the browser drop the connection in ~3 ms. `proxy.py` now echoes it back.

### 5.11 Demo venv conflicts with the main venv
`demo/requirements.txt` pins `huggingface_hub[oauth]>=0.30,<1.0`; installing it into the main venv
downgraded the hub package and broke `transformers`
(`ImportError: cannot import name 'is_offline_mode'`).
**Fix:** the demo has its **own** venv at `demo\.venv`.

### 5.12 Qwen3-TTS crashed loading: access violation in `torch_cpu.dll` ← **the important one**

Loading `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` died instantly, exit code 5, **no Python traceback**.
Two misleading symptoms preceded the real diagnosis:

1. `OSError: The paging file is too small (os error 1455)` — sent us chasing page-file size. It was
   a red herring: the failure persisted with **8.9 GB of free commit**.
2. Silent exit 5. `python -X faulthandler` was required to see anything at all, and the Windows
   Application event log gave the exception code:

```
Faulting module: torch_cpu.dll   Exception code: 0xc0000005 (access violation)
  torch/storage.py:471 in __getitem__
  transformers/core_model_loading.py:1238 in _materialize_copy
```

**Root cause:** the checkpoint is a **single 3.83 GB `model.safetensors`**. transformers memory-maps
it and materializes tensors out of that one huge mapping. On a **4 GB-RAM** box the page-in fails,
and Windows surfaces that as an access violation rather than a clean `MemoryError`.

Two things it was **not** — both tested and ruled out:
- *Not* concurrency. Forcing `transformers.core_model_loading.GLOBAL_WORKERS = 1`
  (it defaults to `min(4, os.cpu_count())`) changed nothing.
- *Not* a corrupt download. Reading all **404 tensors one at a time** via
  `safe_open(...).get_tensor(k)` succeeded — full 3.83 GB in **4 seconds**. Small sequential reads
  are fine; one giant mapping is not.

**Fix — re-shard the checkpoint into 350 MB shards** so each mapping stays small:

```
C:\Users\ali\reshard.py   →   C:\Users\ali\models\Qwen3-TTS-1.7B-CustomVoice-sharded
```
It streams tensor-by-tensor from the original file and writes 11 shards plus
`model.safetensors.index.json`. After that the model loads in ~36 s and captures CUDA graphs.

Two things the reshard script must get right:
- **Copy the `speech_tokenizer/` subdirectory** (the 682 MB codec). A first pass skipped
  directories and produced a model that loaded but had no codec.
- Copy every non-safetensors file (`config.json`, `generation_config.json`, `vocab.json`,
  `merges.txt`, `preprocessor_config.json`, `tokenizer_config.json`).

Point the server at the sharded directory with `--qwen3_tts_model_name`. The original HF cache entry
can then be deleted (reclaims 4.21 GB).

### 5.13 `ValueError: Unsupported languages: ['en']`
Qwen3-TTS wants **full language names**, not ISO codes:
`'auto', 'chinese', 'english', 'french', 'german', 'italian', 'japanese', 'korean', 'portuguese', 'russian', 'spanish'`.
The CLI default `--qwen3_tts_language auto` is fine; only explicit values need care.

### 5.14 Kokoro shells out to `uv` at runtime
If you ever want Kokoro (installed and verified working, `RTF 0.06`): its `misaki` G2P tries to
`uv pip install` the spaCy English model on first use and fails with
`error: No virtual environment found`.
**Fix:** pre-install it — `uv pip install <en_core_web_sm-3.8.0 wheel URL>`.
Swap in with `--tts kokoro --kokoro_device cuda --kokoro_voice bm_fable`.

### 5.15 Disk pressure and what is safe to delete
The C: drive ran down to 2.5 GB free, which also starves the page file. Reclaimed ~8 GB from:

| Item | Freed | Note |
|---|---|---|
| `models--nvidia--parakeet-tdt-0.6b-v3` | 2.34 GB | never used (ruled out on RAM) |
| whisper-small duplicate weight formats | 2.90 GB | `hf download` pulls `.h5` + `.bin` + `.msgpack` alongside `model.safetensors`; only the safetensors is needed |
| original Qwen3-TTS cache entry | 4.21 GB | superseded by the sharded copy |
| `whisper-tiny`, `whisper-tiny.en` | 0.28 GB | superseded by whisper-small |

`uv cache clean` is **not** usable here — it fails with `Access is denied` on
`torch/lib/cudnn_cnn64_9.dll`, and cache entries are hardlinked into the venv, so clearing it
frees far less than its reported size.

---

## 6. Files created (none of the repo was modified)

`git status` shows only `?? demo/proxy.py` — **zero changes to tracked files**.

| Path | Purpose |
|---|---|
| `demo/proxy.py` | Reverse proxy: serves UI + forwards `/v1/realtime` WS to 8765 (new file) |
| `demo/.venv/` | Isolated venv for the demo server |
| `C:\Users\ali\ngrokbin\ngrok.exe` | ngrok 3.39.11 |
| `C:\Users\ali\runstst\*.bat/.ps1` | Launcher / status / log-collector scripts |
| `C:\Users\ali\run_*.bat` | Scheduled-task launchers |
| `C:\Users\ali\reshard.py` | **Splits the 3.83 GB Qwen3-TTS checkpoint into 11 shards (§5.12)** — also kept at `reshard.py` in this repo folder |
| `C:\Users\ali\models\Qwen3-TTS-1.7B-CustomVoice-sharded\` | The sharded checkpoint the server loads |

**Environment changes:** Node.js 24.19.0 (winget) · torch → `2.11.0+cu126` · firewall rule `s2s-ports`
(TCP 7860, 8765) · Defender exclusion on `ngrokbin` · 4 scheduled tasks
(`s2sRun`, `s2sDemo`, `s2sProxy`, `s2sNgrok`, all S4U — currently stopped, delete with
`schtasks /Delete /TN <name> /F`).

---

## 7. Troubleshooting

```cmd
:: what's listening
netstat -an | findstr LISTENING | findstr "7860 8765 8080 4040"

:: free RAM (KB)
wmic OS get FreePhysicalMemory

:: is the UI configured?
curl -s http://localhost:7860/api/config

:: crash events
powershell -NoProfile -Command "Get-WinEvent -FilterHashtable @{LogName='Application';StartTime=(Get-Date).AddMinutes(-10)} | Where-Object {$_.Id -eq 1000} | Select -First 3 TimeCreated,Message | Format-List"
```

| Symptom | Likely cause |
|---|---|
| Backend dies mid-load, no traceback, RAM < 500 MB | Out of memory — close Chrome, test from phone |
| Backend dies, exit `-1073741510` | Console-close event — check `FOR_DISABLE_CONSOLE_CTRL_HANDLER`, stop SSH polling |
| UI asks for server URL | `SPEECH_TO_SPEECH_URL` not set (wrong shell syntax?) |
| UI spins on "connecting" | URL mismatch with ngrok host, or subprotocol bug |
| `[object Event]` | WebSocket failed — see 5.10 |
| Assistant speaks `<thought>` | Wrong model — use a Gemini model with `reasoning_effort minimal` |

---

## 8. Known limitations

1. **4 GB RAM is still the ceiling**, and it now bites at *model-load* time rather than at runtime —
   once weights are on the GPU, system RAM pressure drops. 8 GB would remove the need for §5.12's
   re-sharding entirely.
2. **TTS RTF is 0.73**, i.e. only ~27 % headroom over realtime. Long replies should stay ahead of
   playback, but this box has no margin for a second concurrent session. It is a single-user setup.
3. **Disk is the new constraint** — ~7 GB free on C:, and the page file competes for it. See §5.15
   before downloading any further models.
4. **ngrok URL changes on restart** (free tier) — Terminal 4's `SPEECH_TO_SPEECH_URL` must be updated to match.
5. **No authentication.** Anyone with the ngrok link can use it and consume the Gemini quota.
   Add `--basic-auth user:pass` to the tunnel if that matters.
6. **The Gemini API key is in plaintext** in the launcher scripts and shell history — rotate it if the
   machine is shared.

---

## 9. Next steps

- [ ] Test `--stt_device cuda` (GPU is idle and the blocker is resolved)
- [ ] Add `HF_TOKEN` to remove hub rate limiting
- [ ] Add ngrok `--basic-auth` before sharing the URL
- [ ] Remove the Defender exclusion when finished with ngrok
- [ ] Consider a RAM upgrade — it unlocks Parakeet + Qwen3-TTS and removes the main instability
