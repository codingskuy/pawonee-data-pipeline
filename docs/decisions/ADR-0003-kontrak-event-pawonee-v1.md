# ADR-0003 — Kontrak event Pawonee v1, amplop idempoten, konsumen tercatat

Status: Diusulkan | Tanggal: 2026-10-21

## Konteks

PWN-DATA-003 (M-006). FSD 30 menetapkan 5 event (`rekomendasi.dihitung`, `resep.dimasak`, `serapan.dihitung`, `profil.disimpan`, `sinyal.diterbitkan`) yang membawa id keluarga, waktu, versi kontrak. KONTEKS 3 menetapkan pola amplop (`event_id`, `schema_version`, `source`, `occurred_at`/`received_at`, `batch_id`, retry 3x 5/30/300 dtk lalu DLQ). Isi payload per event TIDAK didefinisikan di dokumen beku; bentuk di `contracts/pawonee-event-v1.json` adalah ASUMSI untuk dikonfirmasi.

## Keputusan

1. Kontrak mesin-baca: `contracts/pawonee-event-v1.json` (terkunci; uji hash). Event baru / perubahan skema = berkas `pawonee-event-v2.json` + ADR + dual-read 30 hari; berkas lama tidak diedit.
2. Amplop: `event_id` (`evt_YYYYMMDD_NNNNNN`) = kunci idempoten; tabel `event_diterima` PK `event_id`, `ON CONFLICT DO NOTHING` (duplikat diabaikan, mengembalikan False).
3. `source = internal`: nilai himpunan KONTEKS 3 (`lumbung, titipo, pasaree, cuaca, internal`) belum memuat `pawonee`.
4. Konsumen tercatat: `sinyal.diterbitkan` -> `pedaree` + `internal`; empat event lain -> `internal`.
5. Pengiriman: percobaan awal + 3 retry (jeda 5/30/300 dtk), lalu tabel `event_dlq`.
6. Event Pawonee belum terdaftar di registry Titeny (11 event, KONTEKS 3); pendaftaran butuh keputusan TownHall (lihat ADR-0001).

## Konsekuensi

- `sinyal.diterbitkan` (event) berbeda dari topik data `sinyal.pedaree.v1` (PWN-DATA-002); belum ada kode yang menerbitkan event ini dari pipa sinyal (di luar lingkup tiket).
- Penerbit event lain adalah backend/klien, bukan pipa ini; pipa hanya memvalidasi dan mencatat.
