@echo off
cd /d "%~dp0"
echo Open http://127.0.0.1:8765 after the READY message.
"..\..\runtime\python\python.exe" run.py
pause
