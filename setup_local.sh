#!/usr/bin/env bash
# ============================================================================
# VACA & GENTILE ERP - Setup rapido para desarrollo local (Linux / Mac)
# ============================================================================
set -e

echo ""
echo "=== VACA & GENTILE ERP - Setup Local ==="
echo ""

# Verificar Python 3.11+
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] python3 no encontrado. Instala Python 3.11+"
    exit 1
fi

PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "[OK] Python $PYVER encontrado"

# Crear entorno virtual
if [ ! -d ".venv" ]; then
    echo "[INFO] Creando entorno virtual..."
    python3 -m venv .venv
    echo "[OK] Entorno virtual creado en .venv/"
else
    echo "[OK] Entorno virtual ya existe"
fi

# Activar entorno virtual
source .venv/bin/activate

# Instalar dependencias
echo "[INFO] Instalando dependencias..."
pip install -r requirements.txt --quiet
echo "[OK] Dependencias instaladas"

# Crear .env si no existe
if [ ! -f ".env" ]; then
    echo "[INFO] Creando archivo .env desde .env.example..."
    cp .env.example .env
    echo "[ATENCION] Edita .env y ajusta VG_RUTA_BASE con la ruta real de tus casos"
else
    echo "[OK] Archivo .env ya existe"
fi

echo ""
echo "=== Setup completado ==="
echo ""
echo "Para iniciar la aplicacion:"
echo "  1. Activa el entorno:   source .venv/bin/activate"
echo "  2. Inicia la app:       streamlit run app.py"
echo "  3. Abre en el browser:  http://localhost:8501"
echo ""
echo "RECORDATORIO: Edita .env con la ruta correcta de VG_RUTA_BASE antes de iniciar."
echo ""
