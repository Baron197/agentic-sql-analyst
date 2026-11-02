-- app: the API's own tables (users and stored runs). Never readable by the agent.
-- Created by `poe app-setup`; `db-load` does not touch it, so stored runs survive a reload.

CREATE SCHEMA IF NOT EXISTS app;
REVOKE ALL ON SCHEMA app FROM PUBLIC;

CREATE TABLE IF NOT EXISTS app.users (
    user_id       text PRIMARY KEY,                -- the sign-in email, e.g. analyst@demo
    display_name  text NOT NULL,
    password_hash text NOT NULL,                   -- argon2id
    role          text NOT NULL CHECK (role IN ('analyst', 'manager')),
    region_ids    integer[],                       -- NULL = all regions
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.runs (
    run_id             text PRIMARY KEY,
    user_id            text NOT NULL REFERENCES app.users (user_id),
    created_at         timestamptz NOT NULL DEFAULT now(),
    status             text NOT NULL,
    question           text NOT NULL,
    provider           text NOT NULL,
    model              text NOT NULL,
    keyless            boolean NOT NULL,
    llm_calls          integer NOT NULL,
    input_tokens       integer NOT NULL,
    output_tokens      integer NOT NULL,
    cache_read_tokens  integer NOT NULL,
    cache_write_tokens integer NOT NULL,
    cost_usd           numeric(14, 8) NOT NULL,
    elapsed_ms         double precision NOT NULL,
    record             jsonb NOT NULL                -- the full AgentResult (rows trimmed)
);
-- A demo sign-in's browser session: its history shows only its own runs (D048). NULL for
-- password sign-ins, which see all of the user's runs.
ALTER TABLE app.runs ADD COLUMN IF NOT EXISTS session_id text;
-- A live run refused by the rules makes no model call and used to be stored as keyless.
-- Keyless means the stand-in model answered, so only the `fake` provider is keyless (D051).
UPDATE app.runs SET keyless = false, record = jsonb_set(record, '{usage,keyless}', 'false')
    WHERE keyless AND provider <> 'fake';
CREATE INDEX IF NOT EXISTS runs_user_created ON app.runs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS runs_session_created ON app.runs (session_id, created_at DESC)
    WHERE session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS runs_created ON app.runs (created_at);

-- The API's login reads users and appends runs; it cannot update or delete anything,
-- and has no access to analytics, core, rls, or retrieval.
GRANT USAGE ON SCHEMA app TO app_writer;
GRANT SELECT ON app.users TO app_writer;
GRANT SELECT, INSERT ON app.runs TO app_writer;
