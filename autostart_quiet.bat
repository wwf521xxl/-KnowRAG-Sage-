@echo off
chcp 65001 >nul
cd /d %~dp0
start "" /min "%~dp0.venv\Scripts\python.exe" "%~dp0kb_server.py" 8010
start "" /min "%~dp0.venv\Scripts\python.exe" "%~dp0watch.py" --interval 60
