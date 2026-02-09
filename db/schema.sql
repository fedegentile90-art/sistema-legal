-- ============================================================================
-- VACA & GENTILE ERP - Schema PostgreSQL v1.0
-- ============================================================================
-- Schema operativo para backend PostgreSQL DB-first.
-- La app usa `repo.py -> repo_db.py` como backend principal.
-- `DATABASE_URL` debe estar configurada para operacion y suites DB.
--
-- COMPATIBILIDAD: PostgreSQL 12+, Supabase, Render Postgres, Railway
-- EJECUCION: psql -d nombre_db -f schema.sql
-- ============================================================================

-- ============================================================================
-- EXTENSIONES (fuera de transaccion - requiere permisos de superuser/owner)
-- ============================================================================
-- Si falla por permisos, ejecutar manualmente o usar pgcrypto/gen_random_uuid()
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Alternativa si uuid-ossp no esta disponible:
-- CREATE EXTENSION IF NOT EXISTS "pgcrypto";
-- Y reemplazar uuid_generate_v4() por gen_random_uuid() en las tablas

-- ============================================================================
-- INICIO DE TRANSACCION (tablas, triggers, indices, vistas)
-- ============================================================================

BEGIN;

-- ============================================================================
-- FUNCION: Trigger para actualizar updated_at automaticamente
-- ============================================================================
-- IMPORTANTE: Esta funcion DEBE existir antes de crear los triggers
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- TABLA: clients (Clientes)
-- ============================================================================

CREATE TABLE IF NOT EXISTS clients (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(255) NOT NULL,
    type        VARCHAR(50) DEFAULT 'persona_fisica',
    doc_type    VARCHAR(20),
    doc_number  VARCHAR(50),
    email       VARCHAR(255),
    phone       VARCHAR(50),
    address     TEXT,
    status      VARCHAR(20) DEFAULT 'activo',
    notes       TEXT,
    extra       JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Trigger (DROP + CREATE para idempotencia)
DROP TRIGGER IF EXISTS clients_updated_at ON clients;
CREATE TRIGGER clients_updated_at
    BEFORE UPDATE ON clients
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Indices (IF NOT EXISTS para idempotencia)
CREATE INDEX IF NOT EXISTS idx_clients_name ON clients(name);
CREATE INDEX IF NOT EXISTS idx_clients_status ON clients(status);
CREATE INDEX IF NOT EXISTS idx_clients_doc ON clients(doc_type, doc_number);

-- ============================================================================
-- TABLA: cases (Casos / Causas)
-- ============================================================================

CREATE TABLE IF NOT EXISTS cases (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id       UUID REFERENCES clients(id) ON DELETE SET NULL,
    -- Jerarquia filesystem
    year            VARCHAR(4) NOT NULL,
    status          VARCHAR(50) NOT NULL,
    fuero           VARCHAR(100) NOT NULL,
    causa           VARCHAR(255) NOT NULL,
    -- Datos de ficha
    tipo_proceso    VARCHAR(100),
    jurisdiccion    VARCHAR(100),
    organismo       VARCHAR(255),
    expediente      VARCHAR(100),
    caratula        TEXT,
    responsable     VARCHAR(100),
    control         VARCHAR(100),
    evento          TEXT,
    fecha_evento    DATE,
    tarea_pendiente TEXT,
    fecha_tarea     DATE,
    observaciones   TEXT,
    -- Financiero
    monto_demandado     DECIMAL(15, 2),
    honorarios_pactados DECIMAL(15, 2),
    estado_pago         VARCHAR(50) DEFAULT 'Pendiente',
    -- Migracion
    fs_path         TEXT,
    extra           JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

DROP TRIGGER IF EXISTS cases_updated_at ON cases;
CREATE TRIGGER cases_updated_at
    BEFORE UPDATE ON cases
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX IF NOT EXISTS idx_cases_client ON cases(client_id);
CREATE INDEX IF NOT EXISTS idx_cases_year ON cases(year);
CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);
CREATE INDEX IF NOT EXISTS idx_cases_fuero ON cases(fuero);
CREATE INDEX IF NOT EXISTS idx_cases_expediente ON cases(expediente);
CREATE INDEX IF NOT EXISTS idx_cases_responsable ON cases(responsable);
CREATE INDEX IF NOT EXISTS idx_cases_fecha_tarea ON cases(fecha_tarea);
CREATE INDEX IF NOT EXISTS idx_cases_fecha_evento ON cases(fecha_evento);

-- ============================================================================
-- TABLA: documents (Documentos)
-- ============================================================================

CREATE TABLE IF NOT EXISTS documents (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id     UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    filename    VARCHAR(255) NOT NULL,
    doc_type    VARCHAR(50) DEFAULT 'otro',
    description TEXT,
    storage_path TEXT,
    size_bytes  BIGINT,
    mime_type   VARCHAR(100),
    extra       JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

DROP TRIGGER IF EXISTS documents_updated_at ON documents;
CREATE TRIGGER documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX IF NOT EXISTS idx_documents_case ON documents(case_id);
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_documents_filename ON documents(filename);

-- ============================================================================
-- TABLA: tasks (Tareas / Agenda)
-- ============================================================================

CREATE TABLE IF NOT EXISTS tasks (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id     UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    title       VARCHAR(255) NOT NULL,
    description TEXT,
    due_date    DATE,
    priority    VARCHAR(20) DEFAULT 'normal',
    status      VARCHAR(20) DEFAULT 'pendiente',
    assigned_to VARCHAR(100),
    completed_at TIMESTAMPTZ,
    extra       JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

DROP TRIGGER IF EXISTS tasks_updated_at ON tasks;
CREATE TRIGGER tasks_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX IF NOT EXISTS idx_tasks_case ON tasks(case_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks(assigned_to);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);

-- ============================================================================
-- TABLA: audit_log (Log de auditoria)
-- ============================================================================

CREATE TABLE IF NOT EXISTS audit_log (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type VARCHAR(50) NOT NULL,
    entity_id   UUID NOT NULL,
    action      VARCHAR(50) NOT NULL,
    changes     JSONB DEFAULT '{}',
    user_id     VARCHAR(100),
    user_name   VARCHAR(255),
    ip_address  INET,
    user_agent  TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);

-- ============================================================================
-- VISTAS UTILES
-- ============================================================================

CREATE OR REPLACE VIEW v_cases_overdue AS
SELECT
    c.id,
    c.causa,
    c.caratula,
    c.expediente,
    c.responsable,
    c.tarea_pendiente,
    c.fecha_tarea,
    c.fecha_tarea - CURRENT_DATE AS days_overdue,
    cl.name AS client_name
FROM cases c
LEFT JOIN clients cl ON c.client_id = cl.id
WHERE c.fecha_tarea IS NOT NULL
  AND c.fecha_tarea < CURRENT_DATE
  AND c.tarea_pendiente IS NOT NULL
  AND c.tarea_pendiente != ''
ORDER BY c.fecha_tarea ASC;

CREATE OR REPLACE VIEW v_cases_by_status AS
SELECT
    status,
    COUNT(*) AS total,
    COUNT(CASE WHEN fecha_tarea < CURRENT_DATE THEN 1 END) AS overdue
FROM cases
GROUP BY status
ORDER BY status;

CREATE OR REPLACE VIEW v_agenda_week AS
SELECT
    c.id,
    c.causa,
    c.caratula,
    c.expediente,
    c.responsable,
    c.tarea_pendiente,
    c.fecha_tarea,
    c.fecha_tarea - CURRENT_DATE AS days_until,
    cl.name AS client_name
FROM cases c
LEFT JOIN clients cl ON c.client_id = cl.id
WHERE c.fecha_tarea IS NOT NULL
  AND c.fecha_tarea >= CURRENT_DATE
  AND c.fecha_tarea <= CURRENT_DATE + INTERVAL '7 days'
  AND c.tarea_pendiente IS NOT NULL
  AND c.tarea_pendiente != ''
ORDER BY c.fecha_tarea ASC;

-- ============================================================================
-- FIN DEL SCHEMA
-- ============================================================================

COMMIT;
