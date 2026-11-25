# 把 data\inbox 共享成网络文件夹（需管理员）
$path = "D:\知识库问答系统\data\inbox"
$name = "KB-Inbox"

if (-not (Test-Path $path)) { New-Item -ItemType Directory -Path $path -Force | Out-Null }

$existing = Get-SmbShare -Name $name -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "share already exists: $name"
} else {
    New-SmbShare -Name $name -Path $path -FullAccess "Everyone" -Description "知识库收件箱：拖文件进来即自动入库" | Out-Null
    Write-Host "share created: $name -> $path"
}

# 放行文件共享防火墙规则
Set-NetFirewallRule -DisplayGroup "文件和打印机共享" -Enabled True -ErrorAction SilentlyContinue
Set-NetFirewallRule -DisplayGroup "File and Printer Sharing" -Enabled True -ErrorAction SilentlyContinue

# 关闭密码保护共享（让同网段设备免账号访问）
$reg = "HKLM:\SYSTEM\CurrentControlSet\Control\Lsa"
Set-ItemProperty -Path $reg -Name "everyoneincludesanonymous" -Value 1 -Type DWord -ErrorAction SilentlyContinue
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters" -Name "restrictnullsessaccess" -Value 0 -Type DWord -ErrorAction SilentlyContinue

Get-SmbShare -Name $name | Select-Object Name, Path, Description | Format-List
