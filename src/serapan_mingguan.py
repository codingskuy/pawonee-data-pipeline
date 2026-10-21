"""Agregat serapan mingguan Pawonee (BRD 30 BR-301..BR-304): serapan, rasio, waste, nilai hemat.

Aritmetika integer penuh (gram, rupiah, basis poin): tanpa float, tanpa tebakan.
Periode: Senin 00.00 sampai Minggu 23.59 WIB; keluarga baru diukur mulai minggu kedua.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

WIB = timezone(timedelta(hours=7))

AMBANG_SERAPAN_G = 1_500
AMBANG_RASIO_BP = 8_000  # 80%
AMBANG_WASTE_G = 300
AMBANG_PROGRAM_SERAPAN_G = 150_000  # 150 kg/minggu (agregat program 100 keluarga)
AMBANG_PROGRAM_HEMAT_RP = 9_000_000
FAKTOR_HEMAT_PERSEN = 60  # G2 dihargai 60% dari harga normal
HARGA_RATA_RATA_PER_GRAM = 100  # Rp/g, acuan agregat program BRD 30 (150.000 g x Rp100 x 0,6)
GRADE_G2 = ("G2-V", "G2-U", "G2-S")


def senin_dari(tanggal: date) -> date:
    return tanggal - timedelta(days=tanggal.weekday())


def batas_minggu_wib(senin: date) -> tuple[datetime, datetime]:
    """[Senin 00.00 WIB, Senin berikutnya 00.00 WIB) -- setara Minggu 23.59:59 WIB."""
    if senin.weekday() != 0:
        raise ValueError("minggu_mulai harus hari Senin")
    awal = datetime(senin.year, senin.month, senin.day, tzinfo=WIB)
    return awal, awal + timedelta(days=7)


def minggu_terakhir_selesai(sekarang: datetime) -> date:
    """Senin dari minggu WIB terakhir yang sudah tertutup pada `sekarang`."""
    hari_ini = sekarang.astimezone(WIB).date()
    return senin_dari(hari_ini) - timedelta(days=7)


def keluarga_diukur(terdaftar_pada: datetime, senin: date) -> bool:
    """Minggu pendaftaran = adaptasi; diukur mulai minggu kedua."""
    return senin > senin_dari(terdaftar_pada.astimezone(WIB).date())


def nilai_hemat(gram: int, harga_per_gram: int = HARGA_RATA_RATA_PER_GRAM) -> int:
    """gram x harga pasar per gram x 0,6, dibulatkan ke bawah (rupiah integer)."""
    return gram * harga_per_gram * FAKTOR_HEMAT_PERSEN // 100


def rasio_bp(serapan_g: int, waste_g: int) -> int | None:
    total = serapan_g + waste_g
    return None if total == 0 else serapan_g * 10_000 // total


def hitung_keluarga(
    masak: Iterable[dict[str, Any]],
    busuk: Iterable[dict[str, Any]],
    harga_per_gram: int = HARGA_RATA_RATA_PER_GRAM,
) -> dict[str, Any]:
    """Metrik satu keluarga satu minggu. `masak`: baris riwayat_masak minggu itu (urut kronologis);
    `busuk`: baris laporan_busuk minggu itu. Tanda ganda resep+hari sama dihitung sekali (BR-304);
    hanya grade G2 yang dihitung sebagai waste."""
    terlihat: set[tuple[str, str]] = set()
    serapan = 0
    for b in masak:
        kunci = (b["resep_id"], str(b["tanggal"]))
        if kunci in terlihat:
            continue
        terlihat.add(kunci)
        serapan += int(b["gram_g2_terserap"])
    waste = sum(int(b["gram"]) for b in busuk if b["kode_grade"] in GRADE_G2)
    r = rasio_bp(serapan, waste)
    return {
        "serapan_g": serapan,
        "waste_dapur_g": waste,
        "rasio_bp": r,
        "nilai_hemat_rp": nilai_hemat(serapan, harga_per_gram),
        "memenuhi_serapan": serapan >= AMBANG_SERAPAN_G,
        "memenuhi_rasio": None if r is None else r >= AMBANG_RASIO_BP,
        "memenuhi_waste": waste <= AMBANG_WASTE_G,
    }


def hitung_program(hasil: Iterable[dict[str, Any]]) -> dict[str, Any]:
    hasil = list(hasil)
    serapan = sum(h["serapan_g"] for h in hasil)
    waste = sum(h["waste_dapur_g"] for h in hasil)
    hemat = sum(h["nilai_hemat_rp"] for h in hasil)
    return {
        "jumlah_keluarga_diukur": len(hasil),
        "serapan_g": serapan,
        "waste_dapur_g": waste,
        "rasio_bp": rasio_bp(serapan, waste),
        "nilai_hemat_rp": hemat,
        "keluarga_memenuhi_serapan": sum(1 for h in hasil if h["memenuhi_serapan"]),
        "keluarga_memenuhi_rasio": sum(1 for h in hasil if h["memenuhi_rasio"]),
        "keluarga_memenuhi_waste": sum(1 for h in hasil if h["memenuhi_waste"]),
        "memenuhi_target_serapan": serapan >= AMBANG_PROGRAM_SERAPAN_G,
        "memenuhi_target_hemat": hemat >= AMBANG_PROGRAM_HEMAT_RP,
    }


_SQL_KELUARGA = "SELECT keluarga_id, dibuat_pada FROM profil_keluarga ORDER BY keluarga_id"
_SQL_MASAK = """
SELECT keluarga_id, resep_id, gram_g2_terserap, tanggal FROM riwayat_masak
WHERE tanggal >= %s AND tanggal < %s ORDER BY keluarga_id, id
"""
_SQL_BUSUK = """
SELECT keluarga_id, nama_bahan, gram, kode_grade FROM laporan_busuk
WHERE tanggal >= %s AND tanggal < %s
"""
_SQL_UPSERT_KELUARGA = """
INSERT INTO agregat_serapan_mingguan
    (keluarga_id, minggu_mulai, serapan_g, waste_dapur_g, rasio_bp, nilai_hemat_rp,
     memenuhi_serapan, memenuhi_rasio, memenuhi_waste)
VALUES (%(keluarga_id)s, %(minggu_mulai)s, %(serapan_g)s, %(waste_dapur_g)s, %(rasio_bp)s,
        %(nilai_hemat_rp)s, %(memenuhi_serapan)s, %(memenuhi_rasio)s, %(memenuhi_waste)s)
ON CONFLICT (keluarga_id, minggu_mulai) DO UPDATE SET
    serapan_g = EXCLUDED.serapan_g, waste_dapur_g = EXCLUDED.waste_dapur_g,
    rasio_bp = EXCLUDED.rasio_bp, nilai_hemat_rp = EXCLUDED.nilai_hemat_rp,
    memenuhi_serapan = EXCLUDED.memenuhi_serapan, memenuhi_rasio = EXCLUDED.memenuhi_rasio,
    memenuhi_waste = EXCLUDED.memenuhi_waste, dihitung_pada = now()
"""
_SQL_UPSERT_PROGRAM = """
INSERT INTO agregat_serapan_program
    (minggu_mulai, jumlah_keluarga_diukur, serapan_g, waste_dapur_g, rasio_bp, nilai_hemat_rp,
     keluarga_memenuhi_serapan, keluarga_memenuhi_rasio, keluarga_memenuhi_waste,
     memenuhi_target_serapan, memenuhi_target_hemat)
VALUES (%(minggu_mulai)s, %(jumlah_keluarga_diukur)s, %(serapan_g)s, %(waste_dapur_g)s, %(rasio_bp)s,
        %(nilai_hemat_rp)s, %(keluarga_memenuhi_serapan)s, %(keluarga_memenuhi_rasio)s,
        %(keluarga_memenuhi_waste)s, %(memenuhi_target_serapan)s, %(memenuhi_target_hemat)s)
ON CONFLICT (minggu_mulai) DO UPDATE SET
    jumlah_keluarga_diukur = EXCLUDED.jumlah_keluarga_diukur, serapan_g = EXCLUDED.serapan_g,
    waste_dapur_g = EXCLUDED.waste_dapur_g, rasio_bp = EXCLUDED.rasio_bp,
    nilai_hemat_rp = EXCLUDED.nilai_hemat_rp,
    keluarga_memenuhi_serapan = EXCLUDED.keluarga_memenuhi_serapan,
    keluarga_memenuhi_rasio = EXCLUDED.keluarga_memenuhi_rasio,
    keluarga_memenuhi_waste = EXCLUDED.keluarga_memenuhi_waste,
    memenuhi_target_serapan = EXCLUDED.memenuhi_target_serapan,
    memenuhi_target_hemat = EXCLUDED.memenuhi_target_hemat, dihitung_pada = now()
"""


def hitung_minggu(conn, senin: date, harga_per_gram: int = HARGA_RATA_RATA_PER_GRAM) -> dict[str, Any]:
    """Hitung & upsert agregat satu minggu (idempoten: hitung ulang menimpa, tak menggandakan).

    `tanggal` pada riwayat_masak/laporan_busuk adalah tanggal WIB. Satu transaksi.
    """
    batas_minggu_wib(senin)  # validasi hari Senin
    akhir = senin + timedelta(days=7)
    hasil: dict[str, dict[str, Any]] = {}
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(_SQL_KELUARGA)
            diukur = [k for k, dibuat in cur.fetchall() if keluarga_diukur(dibuat, senin)]
            cur.execute(_SQL_MASAK, (senin, akhir))
            masak: dict[str, list] = {}
            for k, resep, gram, tgl in cur.fetchall():
                masak.setdefault(k, []).append({"resep_id": resep, "gram_g2_terserap": gram, "tanggal": tgl})
            cur.execute(_SQL_BUSUK, (senin, akhir))
            busuk: dict[str, list] = {}
            for k, nama, gram, grade in cur.fetchall():
                busuk.setdefault(k, []).append({"nama_bahan": nama, "gram": gram, "kode_grade": grade})
            for k in diukur:
                h = hitung_keluarga(masak.get(k, []), busuk.get(k, []), harga_per_gram)
                hasil[k] = h
                cur.execute(_SQL_UPSERT_KELUARGA, {**h, "keluarga_id": k, "minggu_mulai": senin})
            program = hitung_program(hasil.values())
            cur.execute(_SQL_UPSERT_PROGRAM, {**program, "minggu_mulai": senin})
    return program
