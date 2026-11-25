# 创建共享专用账号并授权（需管理员）
$name = "KB-Inbox"
$user = "kb"
$pass = $env:KB_SHARE_PASS

$exists = Get-LocalUser -Name $user -ErrorAction SilentlyContinue
if (-not $exists) {
    New-LocalUser -Name $user -Password (ConvertTo-SecureString $pass -AsPlainText -Force) `
        -FullName "Knowledge Base" -Description "知识库共享账号" -PasswordNeverExpires | Out-Null
    Add-LocalGroupMember -Group "Users" -Member $user -ErrorAction SilentlyContinue
    Write-Host "user created: $user"
} else {
    Write-Host "user exists: $user"
}

Grant-SmbShareAccess -Name $name -AccountName "$env:COMPUTERNAME\$user" -AccessRight Full -Force | Out-Null
Revoke-SmbShareAccess -Name $name -AccountName "Everyone" -Force -ErrorAction SilentlyContinue | Out-Null
Write-Host "granted: $env:COMPUTERNAME\$user -> $name"
Get-SmbShareAccess -Name $name | Select-Object Name, AccountName, AccessControlType, AccessRight | Format-Table -AutoSize
