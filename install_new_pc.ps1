#Requires -Version 5.1
<#
  在另一台 Windows 电脑上安装知识库（离线、免联网）
  用法：
    右键「使用 PowerShell 运行」，或：
    powershell -ExecutionPolicy Bypass -File install_new_pc.ps1
  可选参数：
    -Python "D:\python310\python.exe"   # 指定 Python 3.10
#>
param(
    [string]$Python = "D:\python310\python.exe"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "== 1/5 检查 Python ==" -ForegroundColor Cyan
if (-not (Test-Path $Python)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $Python = $cmd.Source } else { throw "找不到 Python 3.10，请先安装并重新运行" }
}
$ver = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Host "使用 Python $ver ($Python)"
if ($ver -ne "3.10") { Write-Warning "建议 3.10，其他版本可能没有对应的二进制包" }

Write-Host "== 2/5 创建虚拟环境 ==" -ForegroundColor Cyan
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & $Python -m venv .venv
}
$venvPy = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "== 3/5 离线安装依赖 ==" -ForegroundColor Cyan
& $venvPy -m pip install --no-index --find-links wheels --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "依赖安装失败，检查 wheels 目录是否完整" }

Write-Host "== 4/5 检查模型 ==" -ForegroundColor Cyan
$whisper = "models\faster-whisper-medium\model.bin"
$bge = "models\bge-small-zh-onnx\model_quantized.onnx"
if (-not (Test-Path $whisper)) { Write-Warning "缺少转写模型：$whisper（可从原机器复制）" }
if (-not (Test-Path $bge)) { Write-Warning "缺少向量模型：$bge" }

Write-Host "== 5/5 修复数据库路径 ==" -ForegroundColor Cyan
& $venvPy fix_paths.py

Write-Host ""
Write-Host "安装完成。" -ForegroundColor Green
Write-Host "启动：双击 start_all.bat（会打开浏览器）"
Write-Host "自启：把 autostart_quiet.bat 放进启动文件夹，或手动运行"
Write-Host "自检：.venv\Scripts\python.exe healthcheck.py"
