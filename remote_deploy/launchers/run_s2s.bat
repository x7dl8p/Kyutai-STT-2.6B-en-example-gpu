@echo off
cd /d C:\Users\ali\speech-to-speech
IF NOT DEFINED GEMINI_API_KEY (echo ERROR: set GEMINI_API_KEY first & exit /b 1)
set HF_HOME=C:\Users\Ali\.cache\huggingface
set HF_HUB_DISABLE_XET=1
set CUDA_DEVICE_ORDER=FASTEST_FIRST
set FOR_DISABLE_CONSOLE_CTRL_HANDLER=1
.venv\Scripts\speech-to-speech.exe serve --host 0.0.0.0 --llm_backend chat-completions --model_name "gemini-3.5-flash-lite" --responses_api_base_url "https://generativelanguage.googleapis.com/v1beta/openai/" --responses_api_api_key "%GEMINI_API_KEY%" --responses_api_reasoning_effort minimal --responses_api_stream --stream_batch_sentences 1 --no_enable_live_transcription --stt whisper --stt_model_name openai/whisper-small --stt_device cuda:1 --stt_torch_dtype float16 --tts qwen3 --qwen3_tts_model_name "C:\Users\ali\models\Qwen3-TTS-1.7B-CustomVoice-sharded" --qwen3_tts_device cuda --qwen3_tts_dtype float16 --qwen3_tts_backend torch --qwen3_tts_attn_implementation sdpa --qwen3_tts_streaming_chunk_size 10 --no_qwen3_tts_non_streaming_mode > C:\Users\ali\s2s.log 2>&1
