-- Agregat serapan mingguan Pawonee (BRD 30 BR-301..BR-304). Lihat docs/decisions/ADR-0004-*.md.

-- Pendaratan laporan busuk dari Pedaree (diisi dari API/event Pedaree; asumsi, lihat ADR-0004).
CREATE TABLE IF NOT EXISTS laporan_busuk (
    id BIGSERIAL PRIMARY KEY,
    keluarga_id TEXT NOT NULL,
    nama_bahan TEXT NOT NULL,
    gram INT NOT NULL CHECK (gram >= 0),
    kode_grade TEXT NOT NULL CHECK (kode_grade IN ('G2-V', 'G2-U', 'G2-S', 'NON-G2')),
    tanggal DATE NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_laporan_busuk_minggu ON laporan_busuk (keluarga_id, tanggal);

CREATE TABLE IF NOT EXISTS agregat_serapan_mingguan (
    keluarga_id TEXT NOT NULL,
    minggu_mulai DATE NOT NULL,              -- Senin (WIB)
    serapan_g INT NOT NULL,
    waste_dapur_g INT NOT NULL,
    rasio_bp INT,                            -- rasio serapan dalam basis poin (0..10000); NULL bila tak ada data
    nilai_hemat_rp BIGINT NOT NULL,
    memenuhi_serapan BOOLEAN NOT NULL,       -- >= 1.500 g
    memenuhi_rasio BOOLEAN,                  -- >= 80%; NULL bila rasio NULL
    memenuhi_waste BOOLEAN NOT NULL,         -- <= 300 g
    dihitung_pada TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (keluarga_id, minggu_mulai)
);

CREATE TABLE IF NOT EXISTS agregat_serapan_program (
    minggu_mulai DATE PRIMARY KEY,
    jumlah_keluarga_diukur INT NOT NULL,
    serapan_g BIGINT NOT NULL,
    waste_dapur_g BIGINT NOT NULL,
    rasio_bp INT,
    nilai_hemat_rp BIGINT NOT NULL,
    keluarga_memenuhi_serapan INT NOT NULL,
    keluarga_memenuhi_rasio INT NOT NULL,
    keluarga_memenuhi_waste INT NOT NULL,
    memenuhi_target_serapan BOOLEAN NOT NULL,  -- >= 150.000 g
    memenuhi_target_hemat BOOLEAN NOT NULL,    -- >= Rp9.000.000
    dihitung_pada TIMESTAMPTZ NOT NULL DEFAULT now()
);
