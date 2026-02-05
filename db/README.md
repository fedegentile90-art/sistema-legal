# Base de Datos PostgreSQL - VACA & GENTILE ERP

## Estado actual

**NO INTEGRADO** - Este schema es preparatorio para una futura migracion.

La aplicacion actualmente usa **filesystem** como persistencia (`fs_repo.py`).
Este schema se activara cuando se configure la variable de entorno `DATABASE_URL`.

## Requisitos de extensiones

| Extension | Uso | Disponibilidad |
|-----------|-----|----------------|
| `uuid-ossp` | `uuid_generate_v4()` para PKs | Supabase ✓, Render ✓, Railway ✓ |

`CREATE EXTENSION` requiere permisos elevados y se ejecuta **fuera** de la transaccion.
Si falla, usar `pgcrypto` con `gen_random_uuid()` (editar las tablas en schema.sql).

## Proposito

Este directorio contiene el schema SQL para migrar el sistema de:
- **Ahora**: Carpetas en filesystem (Windows/OneDrive)
- **Futuro**: Base de datos PostgreSQL (Render, Railway, Supabase, etc.)

## Estructura del schema

### Tablas principales

| Tabla | Descripcion |
|-------|-------------|
| `clients` | Clientes del estudio juridico |
| `cases` | Casos/causas juridicas |
| `documents` | Documentos asociados a casos |
| `tasks` | Tareas y agenda |
| `audit_log` | Log de auditoria de cambios |

### Caracteristicas

- **UUIDs** como claves primarias (portabilidad, no colision)
- **Columna `extra JSONB`** en cada tabla para campos flexibles
- **Triggers `updated_at`** automaticos en todas las tablas
- **Indices** optimizados para consultas frecuentes
- **Vistas** para reportes comunes (tareas vencidas, agenda semanal)

### Mapeo filesystem → base de datos

```
Jerarquia actual:
  AÑO / ESTADO / CLIENTE / FUERO / CAUSA
    └── ficha.json
    └── 01. PRUEBA/
    └── 02. ESCRITOS/
    └── 03. RECIBOS/
    └── 04. OTROS/

Mapeo a tablas:
  cases.year     ← AÑO
  cases.status   ← ESTADO
  clients.name   ← CLIENTE (se creara cliente si no existe)
  cases.fuero    ← FUERO
  cases.causa    ← CAUSA (nombre carpeta)
  cases.*        ← campos de ficha.json
  documents.*    ← archivos en subcarpetas
```

## Como usar (futuro)

### 1. Crear la base de datos

```bash
# En Render/Railway, se crea automaticamente
# En local:
createdb vaca_gentile
psql -d vaca_gentile -f db/schema.sql
```

### 2. Configurar variable de entorno

```bash
# En .env o en el panel de Render:
DATABASE_URL=postgres://user:pass@host:5432/vaca_gentile
```

### 3. Migracion de datos

Cuando se implemente el repositorio SQL, se creara un script de migracion:
```bash
python -m tools.migrate_fs_to_db
```

## Archivos

| Archivo | Descripcion |
|---------|-------------|
| `schema.sql` | DDL completo (tablas, indices, triggers, vistas) |
| `README.md` | Este archivo |

## Notas tecnicas

### Por que JSONB en `extra`?

Permite agregar campos sin modificar el schema:
```sql
-- Agregar campo personalizado a un caso
UPDATE cases
SET extra = extra || '{"prioridad_interna": "alta"}'::jsonb
WHERE id = '...';

-- Consultar campo personalizado
SELECT * FROM cases
WHERE extra->>'prioridad_interna' = 'alta';
```

### Por que UUIDs?

- No dependen de secuencias (facil migracion)
- No revelan informacion de orden
- Funcionan en entornos distribuidos
- Compatibles con sincronizacion offline

### Compatibilidad con filesystem

La columna `cases.fs_path` guarda la ruta original del filesystem.
Esto permite:
- Migracion gradual
- Rollback si hay problemas
- Referencia para archivos que siguen en disco

## Proximos pasos (no implementados)

1. [ ] Crear `db_repo.py` (equivalente a `fs_repo.py` pero con SQL)
2. [ ] Crear script de migracion `migrate_fs_to_db.py`
3. [ ] Modificar `config.py` para detectar `DATABASE_URL`
4. [ ] Factory pattern en `app.py` para elegir repositorio
5. [ ] Tests de integracion con base de datos de prueba

---

**IMPORTANTE**: No modificar archivos existentes hasta que este schema este probado y la migracion este lista.
