# 把服务注册成“开机即启动”（不需要登录），需管理员权限运行
# 用法：右键 → 使用 PowerShell 运行
# 注意：如果已经用了启动文件夹的 KB-Autostart.bat，请二选一，避免开两个服务抢端口。

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $root ".venv\Scripts\python.exe"
$server = Join-Path $root "kb_server.py"
$watch = Join-Path $root "watch.py"

if (-not (Test-Path $py)) { throw "找不到 .venv，请先运行 install_new_pc.ps1" }

$srvCmd = "`"$py`" `"$server`" 8010"
$watchCmd = "`"$py`" `"$watch`" --interval 60"

schtasks /Create /TN "KB-Server" /TR $srvCmd /SC ONSTART /RU SYSTEM /RL HIGHEST /F | Out-Null
schtasks /Create /TN "KB-Watch" /TR $watchCmd /SC ONSTART /RU SYSTEM /RL HIGHEST /F | Out-Null

Write-Host "已注册开机启动任务："
schtasks /Query /TN "KB-Server" /FO LIST | Select-String "任务名|状态|下次运行时间"
schtasks /Query /TN "KB-Watch" /FO LIST | Select-String "任务名|状态|下次运行时间"
Write-Host ""
Write-Host "提示：以 SYSTEM 身份运行，开机即起、不用登录；但转写可能用不到显卡（会回退 CPU）。"
Write-Host "如果这台机器要负责导入视频，建议改用“登录后启动”（启动文件夹），或开启自动登录。"
