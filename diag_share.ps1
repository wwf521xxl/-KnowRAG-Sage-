$out = "D:\知识库问答系统\data\logs\share_diag.txt"
"=== share access ===" | Out-File $out
Get-SmbShareAccess -Name "KB-Inbox" | Format-Table -AutoSize | Out-File $out -Append
"=== user ===" | Out-File $out -Append
Get-LocalUser -Name "kb" | Select-Object Name,Enabled,LastLogon,PasswordRequired | Format-List | Out-File $out -Append
"=== smb server ===" | Out-File $out -Append
Get-SmbServerConfiguration | Select-Object EnableSMB2Protocol,RequireSecuritySignature,EnableSecuritySignature | Format-List | Out-File $out -Append
"=== guest ===" | Out-File $out -Append
Get-LocalUser -Name "Guest" | Select-Object Name,Enabled | Format-List | Out-File $out -Append
"=== net use test ===" | Out-File $out -Append
cmd /c "net use \\127.0.0.1\KB-Inbox /user:kb $env:KB_SHARE_PASS" 2>&1 | Out-File $out -Append
cmd /c "dir \\127.0.0.1\KB-Inbox" 2>&1 | Out-File $out -Append
