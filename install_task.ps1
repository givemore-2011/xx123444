# 注册每日自动采集计划任务（Windows 计划任务）
# 用法：右键「使用 PowerShell 运行」，或在 PowerShell 中执行本脚本
# 卸载：Unregister-ScheduledTask -TaskName "DIYPriceMonitor" -Confirm:$false

$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py  = (Get-Command python).Source
$task = "DIYPriceMonitor"

$action = New-ScheduledTaskAction `
    -Execute "$dir\daily.bat" `
    -WorkingDirectory $dir

# 每天 09:30 跑一次；错过的任务在开机后补跑
$trigger = New-ScheduledTaskTrigger -Daily -At 09:30
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $task -Action $action -Trigger $trigger `
    -Settings $settings -Description "DIY装机价格监控：每日采集硬件参考价" -Force | Out-Null

Write-Host "已注册计划任务：$task（每天 09:30）"
Write-Host "程序：$py"
Write-Host "脚本：$dir\app.py collect"
Write-Host ""
Write-Host "查看/删除："
Write-Host "  Get-ScheduledTask -TaskName $task"
Write-Host "  Unregister-ScheduledTask -TaskName $task -Confirm:`$false"
