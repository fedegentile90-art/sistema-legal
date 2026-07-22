# VACA & GENTILE ERP - Sistema Legal

Sistema de gestión de expedientes y causas legales del estudio **Vaca & Gentile**.
Construido con Python 3.11 + Streamlit.

---

## Setup local rápido

### Requisitos previos

| Herramienta | Versión mínima |
|---|---|
| Python | 3.11 |
| Git | cualquiera |

### Windows (recomendado)

```bat
git clone https://github.com/fedegentile90-art/sistema-legal.git
cd sistema-legal
setup_local.bat
```

El script crea el entorno virtual, instala dependencias y genera el `.env`.

### Linux / Mac

```bash
git clone https://github.com/fedegentile90-art/sistema-legal.git
cd sistema-legal
chmod +x setup_local.sh
./setup_local.sh
```

---

## Configuración

Editar el archivo `.env` (generado por el setup) con la ruta real de los casos:

```env
VG_RUTA_BASE=C:\Users\TU_USUARIO\Desktop\Derecho y Comunidad Ética\01. Clientes y Casos
```

Ver `.env.example` para todas las opciones disponibles.

---

## Iniciar la aplicación

```bash
# Activar entorno virtual
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux / Mac

# Correr la app
streamlit run app.py
```

Abre el browser en **http://localhost:8501**

---

## Variables de entorno

| Variable | Obligatorio | Descripción |
|---|---|---|
| `VG_RUTA_BASE` | Sí | Carpeta raíz con los casos organizados por año |
| `DATABASE_URL` | No | PostgreSQL. Sin esto, usa filesystem como persistencia |
| `VG_DEBUG` | No | Poner `1` para logs detallados |

---

## Estructura de carpetas de casos

La app espera la siguiente jerarquía en `VG_RUTA_BASE`:

```
VG_RUTA_BASE/
├── 2024/
│   ├── ACTIVOS/
│   │   └── CIVIL/
│   │       └── GARCIA c/ PEREZ - Daños/
│   │           ├── ficha.json
│   │           └── ...documentos
│   └── ARCHIVADOS/
└── 2025/
    └── ...
```

---

## Base de datos (opcional)

Por defecto la app usa el **filesystem** como persistencia. Para activar PostgreSQL:

1. Crear la base de datos y ejecutar `db/schema.sql`
2. Configurar `DATABASE_URL` en `.env`
3. Reiniciar la app — detecta automáticamente la variable y usa la DB

Ver `db/README.md` para detalles del schema.

---

## Docker (alternativa)

```bash
docker build -t sistema-legal .
docker run -p 8501:8501 \
  -e VG_RUTA_BASE=/casos \
  -v /ruta/local/casos:/casos \
  sistema-legal
```
