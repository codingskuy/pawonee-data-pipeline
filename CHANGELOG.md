# CHANGELOG

Format: [Keep a Changelog](https://keepachangelog.com/id-ID/1.1.0/). Versi mengikuti `versions/` TownHall.

## [Belum dirilis]

### Ditambahkan
- PWN-DATA-004: agregat serapan mingguan (serapan, rasio, waste, nilai hemat; per keluarga + program) ke `agregat_serapan_mingguan`/`agregat_serapan_program`, CLI `--serapan-mingguan` (ADR-0004).
- PWN-DATA-002: pipa `sinyal.pedaree.v1` tiap 15 menit per keluarga ke `sinyal_pedaree`, idempoten per periode (ADR-0002); uji pytest dengan Postgres sementara.

### Diubah
- Skema `sinyal_pedaree` (event_id, schema_version, keluarga_id, periode) dan `config/pipeline.yaml` sumber `riwayat_masak`; `bangun_sinyal` lama (resep populer global) diganti.

## [1.0.0] — 2026-10-14

### Ditambahkan
- Fondasi AI-dev v1.0.0: `AGENTS.md`, `CLAUDE.md`, ADR-0001, `40-TECHSTACK.md`, `60-BLAST-RADIUS.md`.
