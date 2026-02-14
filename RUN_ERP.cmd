@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if /I "%~1"=="ops" goto run_ops
if /I "%~1"=="-DailyOps" goto run_ops
if /I "%~1"=="dailyops" goto run_ops

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0RUN_ERP.ps1"
exit /b %ERRORLEVEL%

:run_ops
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0RUN_ERP.ps1" -DailyOps
exit /b %ERRORLEVEL%
