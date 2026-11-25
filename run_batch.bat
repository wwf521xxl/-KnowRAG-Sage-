@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist data\logs mkdir data\logs
echo [%date% %time%] batch start >> data\logs\batch.log
.venv\Scripts\python.exe batch.py run %* >> data\logs\batch.log 2>&1
echo [%date% %time%] batch exit=%errorlevel% >> data\logs\batch.log
