@echo off
chcp 65001 >nul
title ProfitPulse BI - Omni-Channel Profit, RFM & Inventory Intelligence (Port 8045)
cd /d "%~dp0"
echo ============================================================================
echo   ProfitPulse BI — He Thong Phan Tich Lai Rong, RFM & Ton Kho Da Kenh
echo   URL: http://127.0.0.1:8045
echo ============================================================================
start "" "http://127.0.0.1:8045"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8045
pause
