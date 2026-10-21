-- Tabel keluaran pipa Pawonee untuk konsumen Pedaree (DB `pawonee`).
-- Lihat docs/decisions/ADR-0002-sinyal-pedaree-v1.md untuk bentuk dan kunci idempotensi.

CREATE SEQUENCE IF NOT EXISTS seq_event_pawonee;

CREATE TABLE IF NOT EXISTS sinyal_pedaree (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    topik TEXT NOT NULL DEFAULT 'sinyal.pedaree.v1',
    schema_version TEXT NOT NULL DEFAULT 'v1',
    source TEXT NOT NULL DEFAULT 'internal',
    keluarga_id TEXT NOT NULL,
    periode_mulai TIMESTAMPTZ NOT NULL,
    periode_selesai TIMESTAMPTZ NOT NULL,
    muatan JSONB NOT NULL,
    dibuat_pada TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Idempoten per periode: satu sinyal per keluarga per slot 15 menit.
    CONSTRAINT uq_sinyal_pedaree_periode UNIQUE (keluarga_id, periode_mulai),
    CONSTRAINT ck_sinyal_pedaree_topik CHECK (topik = 'sinyal.pedaree.v1'),
    CONSTRAINT ck_sinyal_pedaree_periode CHECK (periode_selesai > periode_mulai)
);

CREATE INDEX IF NOT EXISTS idx_sinyal_pedaree_waktu ON sinyal_pedaree (dibuat_pada DESC);
CREATE INDEX IF NOT EXISTS idx_sinyal_pedaree_periode ON sinyal_pedaree (periode_mulai DESC);
