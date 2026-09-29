CREATE TABLE IF NOT EXISTS notification_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    notification_key TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('upsert', 'cancel', 'test')),
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Pending'
        CHECK(status IN ('Pending', 'Sent', 'Failed', 'Superseded')),
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    sent_at TEXT,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notification_outbox_delivery
    ON notification_outbox(status, next_attempt_at, created_at);
CREATE INDEX IF NOT EXISTS idx_notification_outbox_key
    ON notification_outbox(notification_key, status);

