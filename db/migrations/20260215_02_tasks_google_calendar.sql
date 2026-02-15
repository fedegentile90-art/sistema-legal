-- SistemaLegal migration
-- 2026-02-15 - Tasks-first agenda + Google Calendar integration

BEGIN;

-- -----------------------------------------------------------------------------
-- Hardening tasks for agenda v2
-- -----------------------------------------------------------------------------

ALTER TABLE tasks
    ALTER COLUMN status SET DEFAULT 'pendiente';

ALTER TABLE tasks
    ALTER COLUMN priority SET DEFAULT 'normal';

ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS extra JSONB DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_tasks_case_due_status ON tasks(case_id, due_date, status);
CREATE INDEX IF NOT EXISTS idx_tasks_updated_at ON tasks(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned_due ON tasks(assigned_to, due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_extra_legacy_source ON tasks((extra->>'legacy_source_case_id'));

-- Enforce one legacy-primary task per case during transition.
CREATE UNIQUE INDEX IF NOT EXISTS ux_tasks_legacy_primary_case
    ON tasks((extra->>'legacy_source_case_id'))
    WHERE (extra ? 'legacy_source_case_id') AND (extra->>'is_primary_legacy') = '1';

-- -----------------------------------------------------------------------------
-- Google Calendar OAuth connections
-- -----------------------------------------------------------------------------

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

CREATE INDEX IF NOT EXISTS idx_gcal_conn_user ON google_calendar_connections(user_id);
CREATE INDEX IF NOT EXISTS idx_gcal_conn_status ON google_calendar_connections(status);
CREATE UNIQUE INDEX IF NOT EXISTS ux_gcal_conn_user_calendar
    ON google_calendar_connections(user_id, calendar_id);

-- -----------------------------------------------------------------------------
-- Google event mapping to internal tasks
-- -----------------------------------------------------------------------------

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

CREATE INDEX IF NOT EXISTS idx_gcal_map_task ON google_calendar_event_map(task_id);
CREATE INDEX IF NOT EXISTS idx_gcal_map_conn ON google_calendar_event_map(connection_id);
CREATE INDEX IF NOT EXISTS idx_gcal_map_event ON google_calendar_event_map(google_event_id);
CREATE INDEX IF NOT EXISTS idx_gcal_map_updated ON google_calendar_event_map(updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS ux_gcal_map_conn_event
    ON google_calendar_event_map(connection_id, google_event_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_gcal_map_conn_task
    ON google_calendar_event_map(connection_id, task_id);

COMMIT;
