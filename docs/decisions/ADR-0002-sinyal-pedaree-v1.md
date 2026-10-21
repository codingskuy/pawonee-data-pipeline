# ADR-0002 — Bentuk sinyal.pedaree.v1 dan idempotensi per periode

Status: Diusulkan | Tanggal: 2026-10-21

## Konteks

Tiket PWN-DATA-002 (M-006, FR-204): pipa menerbitkan `sinyal.pedaree.v1` tiap 15 menit ke tabel `sinyal_pedaree`. FRD/FSD v1.0.0 hanya menetapkan topik, jadwal, tabel, dan syarat "id keluarga, waktu, versi kontrak". Isi muatan tidak didefinisikan; `pedaree-openapi.yaml` (non-beku) juga belum memiliki endpoint penerima `sinyal.pedaree.v1`. Bentuk di bawah adalah ASUMSI yang harus dikonfirmasi tim Pedaree.

## Keputusan

1. Satu baris per keluarga per slot 15 menit UTC (`:00/:15/:30/:45`), hanya untuk keluarga yang punya `riwayat_masak` di slot itu (tidak ada sinyal nol).
2. Kunci idempoten: `UNIQUE (keluarga_id, periode_mulai)`; `INSERT ... ON CONFLICT DO NOTHING` dalam satu transaksi per slot. Jalankan ulang slot yang sama aman.
3. Kolom: `event_id` (`evt_YYYYMMDD_NNNNNN`, dari sequence `seq_event_pawonee`, KONTEKS §3), `topik`, `schema_version` (`v1`), `source` (`internal`), `keluarga_id`, `periode_mulai/selesai`, `muatan` JSONB, `dibuat_pada`.
4. Muatan v1: `topik, versi_kontrak, keluarga_id, periode_mulai, periode_selesai, gram_g2_terserap_total, resep_dimasak[{resep_id, jiwa, gram_g2_terserap, tanggal}]`. Gram dari `riwayat_masak` saja (bukan klaim pengguna).
5. Slot yang diproses adalah slot terakhir yang sudah tertutup pada saat jalan (`periode_terakhir_selesai`).
6. Asumsi sumber: `riwayat_masak(id, keluarga_id, resep_id, jiwa, gram_g2_terserap, tanggal, dibuat_pada timestamptz)`; skema asli dimiliki `pawonee-backend-service`.

## Konsekuensi

- Skema `sinyal_pedaree` berubah dari stub fondasi (kolom `id, topik, muatan, dibuat_pada`) dan memecahkan konsumen bila sudah ada; stub belum pernah berisi, jadi tidak ada migrasi data. Tabel lama harus di-DROP sebelum `skema.sql` dijalankan.
- Bila Pedaree meminta muatan lain, ubah lewat bump versi `v2` (dual-read 30 hari).
