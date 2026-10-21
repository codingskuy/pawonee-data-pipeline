"""Kontrak event Pawonee berversi, amplop idempoten, dan pengiriman retry + DLQ.

Sumber kebenaran bentuk: `contracts/pawonee-event-v1.json` (terkunci; ubah lewat berkas versi baru).
Pola amplop mengikuti KONTEKS-LINTAS-DIVISI 3 (event_id, schema_version, source, occurred_at/received_at, batch_id).
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable

DIR_KONTRAK = Path(__file__).resolve().parent.parent / "contracts"
SUMBER = "internal"  # KONTEKS 3 belum punya source `pawonee`; lihat ADR-0003.
JEDA_RETRY_DETIK = (5, 30, 300)
POLA_EVENT_ID = re.compile(r"^evt_\d{8}_\d{6}$")
POLA_KELUARGA = re.compile(r"^KEL-\d{4}$")

_TIPE = {
    "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "str": lambda v: isinstance(v, str),
    "bool": lambda v: isinstance(v, bool),
    "num": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
}


class KontrakError(ValueError):
    """Amplop/event melanggar kontrak berversi."""


def muat_kontrak(versi: str) -> MappingProxyType:
    berkas = DIR_KONTRAK / f"pawonee-event-{versi}.json"
    if not berkas.exists():
        raise KontrakError(f"versi kontrak tidak dikenal: {versi}")
    return MappingProxyType(json.loads(berkas.read_text(encoding="utf-8")))


def versi_tersedia() -> list[str]:
    return sorted(p.stem.removeprefix("pawonee-event-") for p in DIR_KONTRAK.glob("pawonee-event-*.json"))


def daftar_event(versi: str = "v1") -> list[str]:
    return list(muat_kontrak(versi)["event"])


def konsumen(event_type: str, versi: str = "v1") -> list[str]:
    return list(_definisi(event_type, versi)["konsumen"])


def _definisi(event_type: str, versi: str) -> dict:
    ev = muat_kontrak(versi)["event"]
    if event_type not in ev:
        raise KontrakError(f"event tidak terdaftar di {versi}: {event_type}")
    return ev[event_type]


def buat_event_id(tanggal: date, urutan: int) -> str:
    if not 0 <= urutan <= 999_999:
        raise KontrakError("urutan event_id harus 0..999999")
    return f"evt_{tanggal:%Y%m%d}_{urutan:06d}"


def _rfc3339(w: datetime) -> str:
    if w.tzinfo is None:
        raise KontrakError("waktu wajib memakai zona waktu")
    return w.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _cek_payload(payload: dict, spesifikasi: dict) -> None:
    if not isinstance(payload, dict):
        raise KontrakError("payload harus objek")
    kurang = [k for k in spesifikasi if k not in payload]
    if kurang:
        raise KontrakError(f"payload kekurangan field: {', '.join(kurang)}")
    lebih = [k for k in payload if k not in spesifikasi]
    if lebih:
        raise KontrakError(f"payload memuat field tak dikenal: {', '.join(lebih)}")
    for k, tipe in spesifikasi.items():
        nullable = tipe.endswith("?")
        cek = _TIPE[tipe.rstrip("?")]
        if payload[k] is None and nullable:
            continue
        if not cek(payload[k]):
            raise KontrakError(f"payload.{k} bertipe salah (diharapkan {tipe})")


def bangun_amplop(
    event_type: str,
    keluarga_id: str,
    payload: dict,
    *,
    event_id: str,
    occurred_at: datetime,
    received_at: datetime | None = None,
    batch_id: str | None = None,
    versi: str = "v1",
) -> dict[str, Any]:
    amplop = {
        "event_id": event_id,
        "event_type": event_type,
        "schema_version": versi,
        "source": SUMBER,
        "keluarga_id": keluarga_id,
        "occurred_at": _rfc3339(occurred_at),
        "received_at": _rfc3339(received_at or datetime.now(timezone.utc)),
        "batch_id": batch_id,
        "payload": payload,
    }
    validasi_amplop(amplop)
    return amplop


def validasi_amplop(amplop: dict) -> None:
    wajib = ("event_id", "event_type", "schema_version", "source", "keluarga_id",
             "occurred_at", "received_at", "payload")
    for k in wajib:
        if amplop.get(k) in (None, ""):
            raise KontrakError(f"amplop kekurangan {k}")
    if not POLA_EVENT_ID.match(amplop["event_id"]):
        raise KontrakError("event_id harus evt_YYYYMMDD_NNNNNN")
    if not POLA_KELUARGA.match(amplop["keluarga_id"]):
        raise KontrakError("keluarga_id harus KEL-NNNN")
    if amplop["source"] != SUMBER:
        raise KontrakError(f"source harus {SUMBER}")
    for k in ("occurred_at", "received_at"):
        try:
            datetime.fromisoformat(amplop[k].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            raise KontrakError(f"{k} bukan RFC3339") from None
    d = _definisi(amplop["event_type"], amplop["schema_version"])
    _cek_payload(amplop["payload"], d["payload"])


def catat_event(conn, amplop: dict) -> bool:
    """Catat event masuk. True bila baru; False bila duplikat (diabaikan, tidak menggandakan)."""
    validasi_amplop(amplop)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO event_diterima (event_id, event_type, schema_version, source, keluarga_id,
                   occurred_at, received_at, batch_id, payload)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT (event_id) DO NOTHING""",
            (amplop["event_id"], amplop["event_type"], amplop["schema_version"], amplop["source"],
             amplop["keluarga_id"], amplop["occurred_at"], amplop["received_at"], amplop["batch_id"],
             json.dumps(amplop["payload"], ensure_ascii=False)),
        )
        return cur.rowcount == 1


def simpan_dlq(conn, amplop: dict, galat: str, percobaan: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO event_dlq (event_id, amplop, galat, percobaan) VALUES (%s,%s::jsonb,%s,%s)",
            (amplop["event_id"], json.dumps(amplop, ensure_ascii=False), galat, percobaan),
        )


def kirim_dengan_retry(
    kirim: Callable[[dict], None],
    amplop: dict,
    dlq: Callable[[dict, str, int], None],
    tidur: Callable[[float], None],
    jeda: tuple[int, ...] = JEDA_RETRY_DETIK,
) -> bool:
    """Coba kirim; gagal -> retry 3x dengan jeda 5/30/300 dtk, lalu DLQ. True bila terkirim."""
    validasi_amplop(amplop)
    percobaan = 0
    while True:
        percobaan += 1
        try:
            kirim(amplop)
            return True
        except Exception as e:  # noqa: BLE001 - semua galat kirim diperlakukan sama
            if percobaan > len(jeda):
                dlq(amplop, f"{type(e).__name__}: {e}", percobaan)
                return False
            tidur(jeda[percobaan - 1])
