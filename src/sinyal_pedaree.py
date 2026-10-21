"""Pipa sinyal `sinyal.pedaree.v1`: agregat serapan G2 per keluarga per slot 15 menit.

Membaca `riwayat_masak` (satu-satunya sumber serapan; bukan klaim pengguna) dan menulis
`sinyal_pedaree` di DB `pawonee`. Idempoten per periode: kunci (keluarga_id, periode_mulai).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

TOPIK = "sinyal.pedaree.v1"
VERSI_KONTRAK = "v1"
SUMBER = "internal"
SLOT = timedelta(minutes=15)

_SQL_BACA = """
SELECT keluarga_id, resep_id, jiwa, gram_g2_terserap, tanggal
FROM riwayat_masak
WHERE dibuat_pada >= %s AND dibuat_pada < %s
ORDER BY keluarga_id, dibuat_pada, id
"""

_SQL_TULIS = """
INSERT INTO sinyal_pedaree
    (event_id, topik, schema_version, source, keluarga_id, periode_mulai, periode_selesai, muatan)
VALUES (
    'evt_' || to_char(%(mulai)s AT TIME ZONE 'UTC', 'YYYYMMDD') || '_'
        || lpad((nextval('seq_event_pawonee') %% 1000000)::text, 6, '0'),
    %(topik)s, %(versi)s, %(sumber)s, %(keluarga_id)s, %(mulai)s, %(selesai)s, %(muatan)s::jsonb
)
ON CONFLICT (keluarga_id, periode_mulai) DO NOTHING
"""


def _utc(waktu: datetime) -> datetime:
    if waktu.tzinfo is None:
        raise ValueError("waktu wajib memakai zona waktu (RFC3339 UTC)")
    return waktu.astimezone(timezone.utc)


def awal_slot(waktu: datetime) -> datetime:
    """Batas bawah slot 15 menit (UTC) yang memuat `waktu`."""
    w = _utc(waktu).replace(second=0, microsecond=0)
    return w.replace(minute=w.minute - w.minute % 15)


def periode_terakhir_selesai(sekarang: datetime) -> tuple[datetime, datetime]:
    """Slot 15 menit terakhir yang sudah tertutup pada `sekarang` -> (mulai, selesai)."""
    selesai = awal_slot(sekarang)
    return selesai - SLOT, selesai


def bangun_sinyal(keluarga_id: str, mulai: datetime, baris: Iterable[dict[str, Any]]) -> dict:
    """Bentuk muatan sinyal satu keluarga untuk satu slot. Fungsi murni.

    Tanda ganda resep + tanggal yang sama dihitung sekali (BR-304) di dalam slot.
    """
    mulai = _utc(mulai)
    terlihat: set[tuple[str, str]] = set()
    dimasak = []
    total = 0
    for b in baris:
        kunci = (b["resep_id"], str(b["tanggal"]))
        if kunci in terlihat:
            continue
        terlihat.add(kunci)
        gram = int(b["gram_g2_terserap"])
        total += gram
        dimasak.append(
            {
                "resep_id": b["resep_id"],
                "jiwa": int(b["jiwa"]),
                "gram_g2_terserap": gram,
                "tanggal": str(b["tanggal"]),
            }
        )
    selesai = mulai + SLOT
    return {
        "topik": TOPIK,
        "versi_kontrak": VERSI_KONTRAK,
        "keluarga_id": keluarga_id,
        "periode_mulai": mulai.isoformat().replace("+00:00", "Z"),
        "periode_selesai": selesai.isoformat().replace("+00:00", "Z"),
        "gram_g2_terserap_total": total,
        "resep_dimasak": dimasak,
    }


def kelompokkan(baris: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    per_keluarga: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for b in baris:
        per_keluarga[b["keluarga_id"]].append(b)
    return per_keluarga


def terbitkan_periode(conn, mulai: datetime) -> int:
    """Terbitkan sinyal untuk slot [mulai, mulai+15 mnt). Kembalikan jumlah baris BARU.

    Satu transaksi: gagal di tengah berarti tidak ada yang tertulis; menjalankan ulang
    periode yang sama tidak menggandakan sinyal (ON CONFLICT DO NOTHING).
    """
    import json

    mulai = _utc(mulai)
    selesai = mulai + SLOT
    baru = 0
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(_SQL_BACA, (mulai, selesai))
            kolom = [d.name for d in cur.description]
            baris = [dict(zip(kolom, r)) for r in cur.fetchall()]
            for keluarga_id, isi in kelompokkan(baris).items():
                muatan = bangun_sinyal(keluarga_id, mulai, isi)
                cur.execute(
                    _SQL_TULIS,
                    {
                        "mulai": mulai,
                        "selesai": selesai,
                        "topik": TOPIK,
                        "versi": VERSI_KONTRAK,
                        "sumber": SUMBER,
                        "keluarga_id": keluarga_id,
                        "muatan": json.dumps(muatan, ensure_ascii=False),
                    },
                )
                baru += cur.rowcount
    return baru
