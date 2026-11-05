@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   DIY 装机价格监控 - 每日更新
echo ============================================
echo.

echo [1/2] 采集价格与资讯
python -u app.py all
if errorlevel 1 (
    echo 采集失败，终止
    exit /b 1
)

echo.
echo [2/2] 推送到 GitHub
set GIT_CONFIG_GLOBAL=%~dp0.gitconfig-empty
git add -A
git commit -m "更新行情数据 %date:~0,10%" >nul 2>&1
git push
if errorlevel 1 (
    echo 推送失败，检查网络或 GitHub 登录状态
    exit /b 1
)
echo.
echo 完成，线上看板约 1 分钟后更新
