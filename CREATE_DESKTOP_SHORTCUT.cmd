@echo off
setlocal EnableExtensions
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0CREATE_DESKTOP_SHORTCUT.ps1" -Force
exit /b %ERRORLEVEL%
