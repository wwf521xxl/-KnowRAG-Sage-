# 连接办公室 Wi-Fi 并记录结果（需管理员）
$log = "D:\知识库问答系统\data\logs\wifi_ip.txt"
netsh wlan connect name="智汇达_总经理室" interface="WLAN" 2>&1 | Out-File $log -Encoding utf8
Start-Sleep -Seconds 10
ipconfig 2>&1 | Out-File $log -Append -Encoding utf8
netsh wlan show interfaces 2>&1 | Out-File $log -Append -Encoding utf8
Write-Host "done"
