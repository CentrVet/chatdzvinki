@echo off
cd /d D:\bot
set "LOG=D:\bot\scheduler.log"
echo. >> "%LOG%"
echo ======== DAILY %date% %time% ======== >> "%LOG%"
"D:\bot\venv\Scripts\python.exe" daily_report.py >> "%LOG%" 2>&1
