# How it works — press record to hearing audio back

## Step by step

- **You click record** → browser asks mic permission → starts capturing your voice (16kHz audio)
- **Audio streams live** over a WebSocket connection to the backend — no waiting for you to finish talking
- **VAD (Silero)** — a small model listens constantly, detects "this is speech" vs silence, marks when you start/stop talking
- **Smart Turn** — a second model decides "are they *done* talking or just pausing?" — prevents cutting you off mid-sentence
- **STT (Whisper-small, on GPU)** — once your turn is judged complete, your speech audio → converted to text, ~200ms on the GPU
- **LLM (Gemini 3.5 Flash Lite, cloud API)** — your text → sent to Google's servers → generates a reply, streamed back sentence by sentence, ~0.9s to first sentence
- **TTS (Qwen3-TTS, on GPU)** — each sentence of the reply → converted to natural speech audio as it arrives, ~700ms to first audio chunk
- **Audio streams back** to your browser over the same WebSocket → plays automatically
- **Barge-in** — if you start talking again while it's still replying, it cancels itself and listens to you instead

---

## The tech stack, plainly

| Piece | What it is | Where it runs |
|---|---|---|
| VAD | Silero — detects speech vs silence | CPU, tiny |
| Turn detection | Smart Turn v3.2 | CPU, tiny |
| Speech→Text | Whisper-small | **GTX 1060 (GPU)** |
| Brain | Gemini 3.5 Flash Lite | Google's cloud (API call) |
| Text→Speech | Qwen3-TTS 1.7B | **RTX 2060 (GPU)** |
| Delivery | WebSocket, one connection each way | ngrok tunnel → your browser |

---

## Configuration, plainly

- Two GPUs split the work so neither runs out of memory — TTS alone uses most of one card
- Streaming is tuned for speed: TTS speaks in small chunks (not waiting for the whole sentence) so you hear the start of the reply sooner
- Live captions **while you talk** are turned off — that feature only works with a different STT model, and forcing it onto Whisper caused it to re-transcribe every half-second, garbling the text
- Everything is reachable from your phone/any device via one public link that tunnels back to this Windows PC

**Link:** https://seventh-manicure-avid.ngrok-free.dev

See [DEPLOYMENT_CONTEXT.md](DEPLOYMENT_CONTEXT.md) for the full deployment record, run commands, and every problem/fix.
