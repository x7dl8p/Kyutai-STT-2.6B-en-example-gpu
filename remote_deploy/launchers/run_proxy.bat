@echo off
cd /d C:\Users\ali\speech-to-speech\demo
set FOR_DISABLE_CONSOLE_CTRL_HANDLER=1
.venv\Scripts\python.exe -m uvicorn --app-dir . proxy:app --host 0.0.0.0 --port 8080 > C:\Users\ali\proxy.log 2>&1
