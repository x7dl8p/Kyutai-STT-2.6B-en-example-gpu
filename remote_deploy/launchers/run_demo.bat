@echo off
cd /d C:\Users\ali\speech-to-speech\demo
set HF_HOME=C:\Users\Ali\.cache\huggingface
set SPEECH_TO_SPEECH_URL=wss://seventh-manicure-avid.ngrok-free.dev/v1/realtime
set FOR_DISABLE_CONSOLE_CTRL_HANDLER=1
.venv\Scripts\python.exe -m uvicorn --app-dir . server:app --host 0.0.0.0 --port 7860 > C:\Users\ali\demo.log 2>&1
