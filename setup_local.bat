@echo off
REM ============================================================================
REM VACA & GENTILE ERP - Setup rapido para desarrollo local (Windows)
REM ============================================================================

echo.
echo === VACA ^& GENTILE ERP - Setup Local ===
echo.

REM Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Instala Python 3.11 desde https://www.python.org
    pause
    exit /b 1
)

REM Verificar version de Python (necesita 3.11+)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% encontrado

REM Crear entorno virtual si no existe
if not exist ".venv" (
    echo [INFO] Creando entorno virtual...
    python -m venv .venv
    echo [OK] Entorno virtual creado en .venv\
) else (
    echo [OK] Entorno virtual ya existe
)

REM Activar entorno virtual
call .venv\Scripts\activate.bat

REM Instalar dependencias
echo [INFO] Instalando dependencias...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias
    pause
    exit /b 1
)
echo [OK] Dependencias instaladas

REM Crear .env si no existe
if not exist ".env" (
    echo [INFO] Creando archivo .env desde .env.example...
    copy .env.example .env >nul
    echo [ATENCION] Edita .env y ajusta VG_RUTA_BASE con la ruta real de tus casos
) else (
    echo [OK] Archivo .env ya existe
)

echo.
echo === Setup completado ===
echo.
echo Para iniciar la aplicacion:
echo   1. Activa el entorno:   .venv\Scripts\activate
echo   2. Inicia la app:       streamlit run app.py
echo   3. Abre en el browser:  http://localhost:8501
echo.
echo RECORDATORIO: Edita .env con la ruta correcta de VG_RUTA_BASE antes de iniciar.
echo.
pause
