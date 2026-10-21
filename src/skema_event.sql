-- Catatan event Pawonee yang diterima pipa (idempoten) dan DLQ. Lihat contracts/pawonee-event-v1.json.

CREATE TABLE IF NOT EXISTS event_diterima (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source TEXT NOT NULL,
    keluarga_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    batch_id TEXT,
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_event_diterima_tipe ON event_diterima (event_type, occurred_at DESC);

CREATE TABLE IF NOT EXISTS event_dlq (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL,
    amplop JSONB NOT NULL,
    galat TEXT NOT NULL,
    percobaan INT NOT NULL,
    dibuat_pada TIMESTAMPTZ NOT NULL DEFAULT now()
);
