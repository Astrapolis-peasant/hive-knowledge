-- Layer 3/4 of the permission model: PostgreSQL roles, raw immutability, task leases.
-- Reference implementation. Apply once per deployment, then never rely on prompt text
-- for anything enforced here.
--
--   psql -v ON_ERROR_STOP=1 -f db/schema.sql
--
-- TigerFS workspaces (kb_git, kb_raw, kb_control) are created by TigerFS itself; this file
-- governs who may reach them and enforces the invariants Git cannot.

BEGIN;

CREATE SCHEMA IF NOT EXISTS kb;

-- ---------------------------------------------------------------- roles

-- NOLOGIN group roles: capability sets, granted to concrete login roles per deployment.
DO $$
BEGIN
  PERFORM 1 FROM pg_roles WHERE rolname = 'kb_reader';
  IF NOT FOUND THEN CREATE ROLE kb_reader NOLOGIN; END IF;
  PERFORM 1 FROM pg_roles WHERE rolname = 'kb_ingest';
  IF NOT FOUND THEN CREATE ROLE kb_ingest NOLOGIN; END IF;
  PERFORM 1 FROM pg_roles WHERE rolname = 'kb_author';
  IF NOT FOUND THEN CREATE ROLE kb_author NOLOGIN; END IF;
  PERFORM 1 FROM pg_roles WHERE rolname = 'kb_release';
  IF NOT FOUND THEN CREATE ROLE kb_release NOLOGIN; END IF;
  PERFORM 1 FROM pg_roles WHERE rolname = 'kb_admin';
  IF NOT FOUND THEN CREATE ROLE kb_admin NOLOGIN; END IF;
END $$;

GRANT USAGE ON SCHEMA kb TO kb_reader, kb_ingest, kb_author, kb_release, kb_admin;

-- ---------------------------------------------------------------- raw store

-- Content-addressed, create-only. The primary key IS the hash, so a rewrite is a new row
-- by definition and an in-place edit is a constraint violation.
CREATE TABLE IF NOT EXISTS kb.raw_object (
  sha256      char(64) PRIMARY KEY CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  media_type  text        NOT NULL,
  byte_length bigint      NOT NULL CHECK (byte_length >= 0),
  body        bytea       NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  -- Authenticated identity, not a claim. Each agent logs in as a role named exactly its
  -- actor id, so current_user IS the actor and a client cannot misattribute a write.
  created_by  text        NOT NULL DEFAULT current_user,
  CONSTRAINT raw_length_matches CHECK (octet_length(body) = byte_length)
);

CREATE OR REPLACE FUNCTION kb.raw_is_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'kb.raw_object is create-only (attempted %) — evidence is never rewritten',
    TG_OP;
END $$;

DROP TRIGGER IF EXISTS raw_object_immutable ON kb.raw_object;
CREATE TRIGGER raw_object_immutable
  BEFORE UPDATE OR DELETE ON kb.raw_object
  FOR EACH ROW EXECUTE FUNCTION kb.raw_is_immutable();

-- Belt and braces: the trigger states intent, the grant removes the capability.
GRANT SELECT ON kb.raw_object TO kb_reader, kb_author, kb_release, kb_admin;
GRANT SELECT, INSERT ON kb.raw_object TO kb_ingest;
REVOKE UPDATE, DELETE, TRUNCATE ON kb.raw_object FROM PUBLIC, kb_reader, kb_ingest,
  kb_author, kb_release;

-- Hash verification helper. Run in the integrity audit; it is the same check
-- checks/kb.py performs against the filesystem raw store.
CREATE OR REPLACE FUNCTION kb.audit_raw_hashes()
RETURNS TABLE (sha256 char(64), actual char(64))
LANGUAGE sql STABLE AS $$
  SELECT r.sha256, encode(digest(r.body, 'sha256'), 'hex')::char(64)
  FROM kb.raw_object r
  WHERE encode(digest(r.body, 'sha256'), 'hex') <> r.sha256;
$$;  -- requires pgcrypto: CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------- publication

-- Append-only audit of what became published knowledge, and by whom.
CREATE TABLE IF NOT EXISTS kb.release_log (
  id            bigserial PRIMARY KEY,
  released_at   timestamptz NOT NULL DEFAULT now(),
  actor         text        NOT NULL DEFAULT current_user,
  task_id       text        NOT NULL,
  branch        text        NOT NULL,
  base_commit   char(40)    NOT NULL,
  result_commit char(40)    NOT NULL,
  validation    jsonb       NOT NULL,
  review_by     text
);

GRANT SELECT ON kb.release_log TO kb_reader, kb_ingest, kb_author, kb_admin;
GRANT SELECT, INSERT ON kb.release_log TO kb_release;
REVOKE UPDATE, DELETE ON kb.release_log FROM PUBLIC, kb_release;

-- ---------------------------------------------------------------- tasks + leases

CREATE TABLE IF NOT EXISTS kb.task (
  id               text PRIMARY KEY,
  actor            text        NOT NULL DEFAULT current_user,
  role             text        NOT NULL,
  team             text        NOT NULL,
  branch           text        NOT NULL UNIQUE,
  worktree         text        NOT NULL,
  base_commit      char(40)    NOT NULL,
  status           text        NOT NULL DEFAULT 'open'
                     CHECK (status IN ('open','submitted','merged','abandoned','expired')),
  review_required  boolean     NOT NULL DEFAULT false,
  opened_at        timestamptz NOT NULL DEFAULT now(),
  lease_expires_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS task_open_idx ON kb.task (status, lease_expires_at);

GRANT SELECT ON kb.task TO kb_reader, kb_admin;
GRANT SELECT, INSERT, UPDATE ON kb.task TO kb_ingest, kb_author, kb_release;

-- An agent may only see and mutate its own task rows, so one agent cannot steal another's
-- lease or worktree.
--
-- This compares `current_user` — the role PostgreSQL authenticated — and NOT a session
-- setting. An earlier version trusted current_setting('kb.actor'), which any session can
-- overwrite with `SET kb.actor = 'someone.else'`, making the policy decorative against
-- exactly the case it was written for. Authenticate, do not ask.
ALTER TABLE kb.task ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS task_own_rows ON kb.task;
CREATE POLICY task_own_rows ON kb.task
  USING (actor = current_user OR pg_has_role(current_user, 'kb_release', 'MEMBER'))
  WITH CHECK (actor = current_user);

-- Expire stale leases so a crashed agent does not hold an area forever. The worktree and
-- its commits survive; only the claim lapses.
CREATE OR REPLACE FUNCTION kb.expire_leases() RETURNS integer
LANGUAGE sql AS $$
  WITH e AS (
    UPDATE kb.task SET status = 'expired'
    WHERE status = 'open' AND lease_expires_at < now()
    RETURNING 1
  ) SELECT count(*)::int FROM e;
$$;

-- Upgrade path for a database created before identity was authenticated.
ALTER TABLE kb.raw_object  ALTER COLUMN created_by SET DEFAULT current_user;
ALTER TABLE kb.task        ALTER COLUMN actor      SET DEFAULT current_user;
ALTER TABLE kb.release_log ALTER COLUMN actor      SET DEFAULT current_user;

COMMIT;

-- ---------------------------------------------------------------- deployment notes
--
-- 1. Create one LOGIN role per agent, named EXACTLY the actor id in governance/roles.yaml,
--    granted exactly one capability role:
--      CREATE ROLE "agent.compile-01" LOGIN PASSWORD :'pw' IN ROLE kb_author;
--    The role name is the identity. Do not set a `kb.actor` session variable: a session can
--    overwrite one, so anything that trusts it can be impersonated. Let the columns default
--    to current_user and let RLS compare current_user.
-- 2. Give the release worker its own role and its own TigerFS mount credential. Nothing
--    else may write the workspace holding refs/heads/main.
-- 3. Keep `restricted` pages in a separate TigerFS workspace with its own credential if
--    read control has to be real rather than advisory.
-- 4. Enable WAL archiving and test point-in-time recovery before ingesting anything you
--    would be unhappy to lose. Git integrity checks are not a backup.
