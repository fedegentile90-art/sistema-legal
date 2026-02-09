@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if /I "%~1"=="ops" goto run_ops
if /I "%~1"=="-DailyOps" goto run_ops
if /I "%~1"=="dailyops" goto run_ops

set "ADDR=localhost"
set "PORT=8501"
set "URL=http://%ADDR%:%PORT%"
set "LOG=%~dp0run_erp.log"

REM Elegir python (preferir venv)
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=%CD%\.venv\Scripts\python.exe"

REM Si ya hay algo escuchando, abrir navegador y salir
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
  start "" "%URL%"
  exit /b 0
)

REM Arrancar streamlit en background (sin ventana nueva)
echo [RUN] %DATE% %TIME% > "%LOG%"
start "" /B "%PY%" -m streamlit run app.py --server.address=%ADDR% --server.port=%PORT% --logger.level=info 1>>"%LOG%" 2>>&1

REM Esperar hasta que responda el puerto (max 20s), y abrir navegador
set /a tries=0
:waitloop
set /a tries+=1
powershell -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing %URL% -TimeoutSec 1; exit 0 } catch { exit 1 }" >nul 2>&1
if %ERRORLEVEL%==0 goto opened
if %tries% GEQ 20 goto failed
timeout /t 1 >nul
goto waitloop

:opened
start "" "%URL%"
exit /b 0

:failed
REM Si falla, mostrar log (solo en error)
echo ERROR: No se pudo abrir %URL% (timeout). Mirar: %LOG%
type "%LOG%"
pause
exit /b 1

:run_ops
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0RUN_ERP.ps1" -DailyOps
exit /b %ERRORLEVEL%
