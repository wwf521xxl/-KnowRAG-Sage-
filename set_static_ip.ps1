# 把 WLAN 设为固定 IP（需管理员）
$log = "D:\知识库问答系统\data\logs\wifi_static.txt"

netsh interface ip set address name="WLAN" static 192.168.0.113 255.255.255.0 192.168.0.1 2>&1 | Out-File $log -Encoding utf8
netsh interface ip set dns name="WLAN" static 192.168.0.1 2>&1 | Out-File $log -Append -Encoding utf8
netsh interface ip add dns name="WLAN" 192.168.1.1 index=2 2>&1 | Out-File $log -Append -Encoding utf8

# 让有线保持默认路由优先，避免 Wi-Fi 抢默认网关
netsh interface ipv4 set interface "WLAN" metric=50 2>&1 | Out-File $log -Append -Encoding utf8

Start-Sleep -Seconds 2
ipconfig 2>&1 | Out-File $log -Append -Encoding utf8
Write-Host "static ip applied"
