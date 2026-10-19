@echo off
cd /d D:\bot
set "LOG=D:\bot\scheduler.log"
echo. >> "%LOG%"
echo ======== %date% %time% ======== >> "%LOG%"
"D:\bot\venv\Scripts\python.exe" main.py >> "%LOG%" 2>&1
