-- Kudos schema: see SPECIFICATION.md section 3.2
DROP TABLE IF EXISTS moderation_log;
DROP TABLE IF EXISTS kudos;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    email          TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    display_name   TEXT    NOT NULL,
    department     TEXT    NOT NULL DEFAULT '',
    password_hash  TEXT    NOT NULL,
    role           TEXT    NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    is_active      INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE kudos (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id          INTEGER NOT NULL REFERENCES users(id),
    recipient_id       INTEGER NOT NULL REFERENCES users(id),
    message            TEXT    NOT NULL CHECK (length(message) BETWEEN 1 AND 500),
    message_normalized TEXT    NOT NULL,
    created_at         TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    is_visible         INTEGER NOT NULL DEFAULT 1 CHECK (is_visible IN (0, 1)),
    is_deleted         INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    moderated_by       INTEGER REFERENCES users(id),
    moderated_at       TEXT,
    moderation_reason  TEXT,
    CHECK (sender_id <> recipient_id)
);

CREATE INDEX idx_kudos_feed      ON kudos (is_visible, is_deleted, created_at DESC);
CREATE INDEX idx_kudos_sender    ON kudos (sender_id, created_at);
CREATE INDEX idx_kudos_recipient ON kudos (recipient_id, created_at);

CREATE TABLE moderation_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kudos_id    INTEGER NOT NULL REFERENCES kudos(id),
    admin_id    INTEGER NOT NULL REFERENCES users(id),
    action      TEXT    NOT NULL CHECK (action IN ('hide', 'unhide', 'delete')),
    reason      TEXT,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX idx_modlog_kudos ON moderation_log (kudos_id, created_at);
