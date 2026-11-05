@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   DIY 装机价格监控 - 每日更新
echo ============================================
echo.

rem 一条命令涵盖：采集价格 + 拉资讯 + 生成看板 + 生成 docs/ + 推 GitHub
rem 推送逻辑统一放在 app.py 的 cmd_push 里，这里不再重复一套 git 命令
python -u app.py daily
if errorlevel 1 (
    echo.
    echo 更新失败，看上面的报错
    exit /b 1
)

echo.
echo 完成，线上看板约 1 分钟后更新
