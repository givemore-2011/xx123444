@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   DIY 装机价格监控
echo ============================================
echo.
python app.py
echo.
pause
