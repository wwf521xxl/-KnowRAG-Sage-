# 把知识库服务注册成 Windows 计划任务（开机自启、SYSTEM 身份、不依赖登录）
$root = "D:\知识库问答系统"
$py = Join-Path $root ".venv\Scripts\python.exe"
$tr = '"' + $py + '" "' + (Join-Path $root "kb_server.py") + '" 8010'

schtasks /Create /TN "KB-Server" /TR $tr /SC ONSTART /RU SYSTEM /RL HIGHEST /F | Out-Null
schtasks /Run /TN "KB-Server" | Out-Null
Start-Sleep -Seconds 4
schtasks /Query /TN "KB-Server" /FO LIST
