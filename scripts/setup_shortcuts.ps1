# 创建桌面/开始菜单快捷方式 + 开机自启（指向控制面板）
$root = "D:\知识库问答系统"
$pyw = Join-Path $root ".venv\Scripts\pythonw.exe"
$app = Join-Path $root "app.py"
$ico = Join-Path $root "app.ico"

$ws = New-Object -ComObject WScript.Shell
function New-KBShortcut([string]$path, [string]$arguments) {
    $s = $ws.CreateShortcut($path)
    $s.TargetPath = $pyw
    $s.Arguments = $arguments
    $s.WorkingDirectory = $root
    $s.IconLocation = $ico
    $s.Description = "知识库"
    $s.Save()
    Write-Host ("created: " + $path)
}

New-KBShortcut ([Environment]::GetFolderPath('Desktop') + "\知识库.lnk") $app
New-KBShortcut ([Environment]::GetFolderPath('Programs') + "\知识库.lnk") $app
New-KBShortcut ([Environment]::GetFolderPath('Startup') + "\KB-Autostart.lnk") ($app + " --minimized")

$oldBat = [Environment]::GetFolderPath('Startup') + "\KB-Autostart.bat"
if (Test-Path $oldBat) { Remove-Item $oldBat -Force; Write-Host "removed old bat" }
