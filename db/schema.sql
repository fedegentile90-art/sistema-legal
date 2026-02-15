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
CREATE INDEX IF NOT EXISTS idx_tasks_case_due_status ON tasks(case_id, due_date, status);
CREATE INDEX IF NOT EXISTS idx_tasks_updated_at ON tasks(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_extra_legacy_source ON tasks((extra->>'legacy_source_case_id'));
CREATE UNIQUE INDEX IF NOT EXISTS ux_tasks_legacy_primary_case
    ON tasks((extra->>'legacy_source_case_id'))
    WHERE (extra ? 'legacy_source_case_id') AND (extra->>'is_primary_legacy') = '1';

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
-- TABLAS: Auth local + RBAC (fase seguridad minima viable)
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username        VARCHAR(120) UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    display_name    VARCHAR(255),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at   TIMESTAMPTZ,
    extra           JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

DROP TRIGGER IF EXISTS users_updated_at ON users;
CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS roles (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(80) UNIQUE NOT NULL,
    description     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS permissions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code            VARCHAR(120) UNIQUE NOT NULL,
    description     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id         UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id         UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id   UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role            VARCHAR(80) NOT NULL,
    ip_address      INET,
    user_agent      TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS google_calendar_connections (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    google_email        VARCHAR(255) NOT NULL DEFAULT '',
    calendar_id         VARCHAR(255) NOT NULL DEFAULT 'primary',
    refresh_token_enc   TEXT NOT NULL DEFAULT '',
    scope               TEXT NOT NULL DEFAULT '',
    sync_token          TEXT NOT NULL DEFAULT '',
    status              VARCHAR(32) NOT NULL DEFAULT 'active',
    extra               JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    last_sync_at        TIMESTAMPTZ
);

DROP TRIGGER IF EXISTS google_calendar_connections_updated_at ON google_calendar_connections;
CREATE TRIGGER google_calendar_connections_updated_at
    BEFORE UPDATE ON google_calendar_connections
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TABLE IF NOT EXISTS google_calendar_event_map (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id                 UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    connection_id           UUID NOT NULL REFERENCES google_calendar_connections(id) ON DELETE CASCADE,
    google_event_id         VARCHAR(255) NOT NULL,
    google_etag             VARCHAR(255) NOT NULL DEFAULT '',
    google_updated_at       TIMESTAMPTZ,
    last_local_updated_at   TIMESTAMPTZ,
    is_deleted              BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

DROP TRIGGER IF EXISTS google_calendar_event_map_updated_at ON google_calendar_event_map;
CREATE TRIGGER google_calendar_event_map_updated_at
    BEFORE UPDATE ON google_calendar_event_map
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_active ON auth_sessions(is_active);
CREATE INDEX IF NOT EXISTS idx_gcal_conn_user ON google_calendar_connections(user_id);
CREATE INDEX IF NOT EXISTS idx_gcal_conn_status ON google_calendar_connections(status);
CREATE UNIQUE INDEX IF NOT EXISTS ux_gcal_conn_user_calendar
    ON google_calendar_connections(user_id, calendar_id);
CREATE INDEX IF NOT EXISTS idx_gcal_map_task ON google_calendar_event_map(task_id);
CREATE INDEX IF NOT EXISTS idx_gcal_map_conn ON google_calendar_event_map(connection_id);
CREATE INDEX IF NOT EXISTS idx_gcal_map_event ON google_calendar_event_map(google_event_id);
CREATE INDEX IF NOT EXISTS idx_gcal_map_updated ON google_calendar_event_map(updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS ux_gcal_map_conn_event
    ON google_calendar_event_map(connection_id, google_event_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_gcal_map_conn_task
    ON google_calendar_event_map(connection_id, task_id);

-- ============================================================================
-- TABLAS: Cadena de custodia documental y eventos de caso
-- ============================================================================

CREATE TABLE IF NOT EXISTS document_versions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id     UUID REFERENCES documents(id) ON DELETE CASCADE,
    case_id         UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    version_number  INTEGER NOT NULL,
    storage_path    TEXT,
    checksum_sha256 VARCHAR(64),
    created_by      VARCHAR(100),
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS case_events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id         UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    event_type      VARCHAR(80) NOT NULL,
    event_payload   JSONB DEFAULT '{}',
    event_at        TIMESTAMPTZ DEFAULT NOW(),
    actor_id        VARCHAR(100),
    actor_role      VARCHAR(80)
);

CREATE INDEX IF NOT EXISTS idx_doc_versions_case ON document_versions(case_id, version_number DESC);
CREATE INDEX IF NOT EXISTS idx_doc_versions_doc ON document_versions(document_id, version_number DESC);
CREATE INDEX IF NOT EXISTS idx_case_events_case ON case_events(case_id, event_at DESC);
CREATE INDEX IF NOT EXISTS idx_case_events_type ON case_events(event_type);

-- Guard de duplicados por jerarquia + causa normalizada (sin bloqueo retroactivo).
CREATE INDEX IF NOT EXISTS idx_cases_duplicate_guard
    ON cases(client_id, year, status, fuero, (lower(trim(causa))));

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
