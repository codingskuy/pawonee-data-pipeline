# ADR-0004 — Agregat serapan mingguan

Status: Diusulkan | Tanggal: 2026-10-21

## Konteks

PWN-DATA-004 (M-007): BRD 30 BR-301..BR-304 menetapkan serapan G2 >= 1.500 g, rasio >= 80%, waste dapur <= 300 g per keluarga per minggu, nilai hemat = gram x harga pasar per gram x 0,6, dan agregat program 100 keluarga (>= 150 kg, >= Rp9.000.000 per minggu). Periode Senin 00.00 - Minggu 23.59 WIB; keluarga baru diukur mulai minggu kedua; tanda ganda resep+hari dihitung sekali.

## Keputusan

1. Aritmetika integer: gram, rupiah (floor), rasio dalam basis poin (`rasio_bp`, 8000 = 80%); rasio NULL bila serapan + busuk = 0.
2. Tabel keluaran `agregat_serapan_mingguan` (PK keluarga_id + minggu_mulai) dan `agregat_serapan_program` (PK minggu_mulai); hitung ulang = upsert (idempoten, menimpa data terlambat), satu transaksi.
3. Keluarga diukur = baris `profil_keluarga` dengan minggu pendaftaran (WIB) < minggu yang dihitung; keluarga tanpa masakan tetap diukur (serapan 0).
4. Waste = jumlah gram `laporan_busuk` ber-grade G2-V/U/S; NON-G2 tidak dihitung.
5. Harga: tanpa rincian bahan di `riwayat_masak`, nilai hemat memakai Rp100/gram (acuan BRD 30: 150.000 g x Rp100 x 0,6 = Rp9.000.000), dapat diganti lewat parameter `harga_per_gram`.
6. Minggu berjalan ditolak CLI (`--serapan-mingguan` hanya minggu WIB yang sudah tertutup).

## Asumsi / hal terbuka

- `laporan_busuk` ada di DB `pawonee` sebagai tabel pendaratan yang diisi dari API/event Pedaree (BR-303 menyebut `laporan_busuk` di Pedaree; `pedaree-openapi.yaml` belum mengekspos busuk per keluarga + grade). Ini menambah tulis ke tabel baru di luar `sinyal_pedaree` (AGENTS aturan 10 menyebut hanya `sinyal_pedaree`): perlu persetujuan.
- `profil_keluarga.dibuat_pada` dan `riwayat_masak.tanggal` (DATE, WIB) diasumsikan.
- Ketidakselarasan dokumen: FSD 20 memberi harga Lumbung G2 per 100 g (wortel 1.200, kentang 1.500, ...) sedangkan metrik/BRD memakai harga pasar (wortel 2.000, kentang 2.500, ...); nilai hemat memakai harga pasar sesuai BR-301.
- Target program berlaku untuk 100 keluarga; kolom `jumlah_keluarga_diukur` disimpan agar pembaca bisa menilai kelayakan perbandingan.

## Konsekuensi

Tiga tabel baru di DB `pawonee`. Pembaca (web riwayat, dasbor) membaca agregat, bukan menghitung ulang.
