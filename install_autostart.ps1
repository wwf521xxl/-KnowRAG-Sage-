# 把「开机自启」写入当前用户的启动文件夹（路径按本机实际位置生成）
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$startup = [Environment]::GetFolderPath('Startup')
$bat = @"
@echo off
cd /d "$root"
start "" /min "$root\.venv\Scripts\python.exe" "$root\kb_server.py" 8010
start "" /min "$root\.venv\Scripts\python.exe" "$root\watch.py" --interval 60
"@
$path = Join-Path $startup 'KB-Autostart.bat'
Set-Content -Path $path -Value $bat -Encoding OEM
Write-Host "已写入：$path"
