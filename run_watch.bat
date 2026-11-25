@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist data\logs mkdir data\logs
.venv\Scripts\python.exe watch.py --interval 60 >> data\logs\watch.log 2>&1
