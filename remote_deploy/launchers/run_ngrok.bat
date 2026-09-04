@echo off
set FOR_DISABLE_CONSOLE_CTRL_HANDLER=1
C:\Users\ali\ngrokbin\ngrok.exe http 127.0.0.1:8080 --log stdout --log-format logfmt > C:\Users\ali\ngrok.log 2>&1
