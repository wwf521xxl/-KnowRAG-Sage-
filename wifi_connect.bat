@echo off
chcp 65001 >nul
netsh wlan connect name="智汇达_总经理室" interface="WLAN"
timeout /t 10 >nul
ipconfig > "D:\知识库问答系统\data\logs\wifi_ip.txt" 2>&1
netsh wlan show interfaces >> "D:\知识库问答系统\data\logs\wifi_ip.txt" 2>&1
