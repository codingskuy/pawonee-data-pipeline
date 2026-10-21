import hashlib
from datetime import date, datetime, timezone

import pytest

import kontrak_event as k
from kontrak_event import KontrakError

UTC = timezone.utc
T = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)
# Hash kunci kontrak v1: mengubah berkas v1 menggagalkan uji ini -> wajib buat berkas v2 + ADR.
SHA256_V1 = "3912ff6dac8638eed5f03507c11a3321725023bd959b8f003af1d7dbafdf463e"

CONTOH = {
    "rekomendasi.dihitung": {"jumlah_item": 5, "mode_tanpa_stok": False},
    "resep.dimasak": {"resep_id": "R-06", "jiwa": 4, "gram_g2_terserap": 400, "tanggal": "2026-10-21"},
    "serapan.dihitung": {"minggu_mulai": "2026-10-19", "serapan_g2_gram": 1600, "waste_dapur_gram": 100,
                         "rasio_serapan": 0.94},
    "profil.disimpan": {"versi_profil": 3},
    "sinyal.diterbitkan": {"sinyal_event_id": "evt_20261021_000001", "periode_mulai": "2026-10-21T10:00:00Z",
                           "periode_selesai": "2026-10-21T10:15:00Z", "gram_g2_terserap_total": 400},
}


def amplop(tipe="resep.dimasak", n=1, **ubah):
    a = k.bangun_amplop(tipe, "KEL-0001", CONTOH[tipe], event_id=k.buat_event_id(date(2026, 10, 21), n),
                        occurred_at=T, received_at=T, batch_id="b1")
    a.update(ubah)
    return a


def test_lima_event_terdokumentasi_persis():
    assert k.daftar_event("v1") == [
        "rekomendasi.dihitung", "resep.dimasak", "serapan.dihitung", "profil.disimpan", "sinyal.diterbitkan"
    ]


def test_berkas_v1_terkunci_hash():
    isi = (k.DIR_KONTRAK / "pawonee-event-v1.json").read_bytes()
    assert hashlib.sha256(isi).hexdigest() == SHA256_V1


def test_versi_baru_hanya_lewat_berkas_baru():
    assert k.versi_tersedia() == ["v1"]
    with pytest.raises(KontrakError):
        k.muat_kontrak("v2")
    with pytest.raises(TypeError):
        k.muat_kontrak("v1")["event"] = {}  # kontrak dibaca-saja


@pytest.mark.parametrize("tipe", list(CONTOH))
def test_tiap_event_membawa_keluarga_waktu_versi(tipe):
    a = amplop(tipe)
    assert a["keluarga_id"] == "KEL-0001"
    assert a["occurred_at"] == "2026-10-21T10:00:00Z"
    assert a["schema_version"] == "v1"
    assert a["event_id"] == "evt_20261021_000001"


def test_konsumen_tercatat_pedaree_untuk_sinyal_internal_lainnya():
    assert "pedaree" in k.konsumen("sinyal.diterbitkan")
    for tipe in CONTOH:
        if tipe != "sinyal.diterbitkan":
            assert k.konsumen(tipe) == ["internal"]


def test_event_id_format():
    assert k.buat_event_id(date(2026, 1, 2), 42) == "evt_20260102_000042"
    with pytest.raises(KontrakError):
        k.buat_event_id(date(2026, 1, 2), 1_000_000)


@pytest.mark.parametrize(
    "ubah",
    [
        {"event_id": "evt_2026_1"},
        {"keluarga_id": "K1"},
        {"event_type": "resep.dihapus"},
        {"schema_version": "v9"},
        {"source": "lumbung"},
        {"occurred_at": "kemarin"},
        {"payload": {"resep_id": "R-06"}},
        {"payload": {**CONTOH["resep.dimasak"], "ekstra": 1}},
        {"payload": {**CONTOH["resep.dimasak"], "jiwa": "4"}},
        {"payload": {**CONTOH["resep.dimasak"], "jiwa": True}},
    ],
)
def test_amplop_tak_sah_ditolak(ubah):
    with pytest.raises(KontrakError):
        k.validasi_amplop(amplop(**ubah))


def test_field_nullable_rasio_boleh_null():
    p = {**CONTOH["serapan.dihitung"], "rasio_serapan": None}
    k.bangun_amplop("serapan.dihitung", "KEL-0001", p, event_id="evt_20261021_000009", occurred_at=T)


def test_waktu_tanpa_zona_ditolak():
    with pytest.raises(KontrakError):
        k.bangun_amplop("profil.disimpan", "KEL-0001", CONTOH["profil.disimpan"],
                        event_id="evt_20261021_000001", occurred_at=datetime(2026, 10, 21))


def test_catat_event_duplikat_diabaikan(conn):
    a = amplop()
    assert k.catat_event(conn, a) is True
    assert k.catat_event(conn, a) is False
    assert conn.execute("SELECT count(*) FROM event_diterima").fetchone()[0] == 1
    assert k.catat_event(conn, amplop(n=2)) is True
    assert conn.execute("SELECT count(*) FROM event_diterima").fetchone()[0] == 2


def test_catat_event_tak_sah_tidak_tertulis(conn):
    with pytest.raises(KontrakError):
        k.catat_event(conn, amplop(keluarga_id="x"))
    assert conn.execute("SELECT count(*) FROM event_diterima").fetchone()[0] == 0


def test_retry_berhasil_pada_percobaan_ketiga_tanpa_dlq():
    gagal, tidur, dlq = {"n": 0}, [], []

    def kirim(_):
        gagal["n"] += 1
        if gagal["n"] < 3:
            raise ConnectionError("putus")

    assert k.kirim_dengan_retry(kirim, amplop(), lambda *a: dlq.append(a), tidur.append) is True
    assert tidur == [5, 30] and dlq == []


def test_retry_tiga_kali_5_30_300_lalu_dlq():
    tidur, dlq, n = [], [], {"n": 0}

    def kirim(_):
        n["n"] += 1
        raise TimeoutError("lambat")

    a = amplop()
    assert k.kirim_dengan_retry(kirim, a, lambda *x: dlq.append(x), tidur.append) is False
    assert n["n"] == 4  # 1 percobaan awal + 3 retry
    assert tidur == [5, 30, 300]
    assert len(dlq) == 1 and dlq[0][0] == a and "TimeoutError" in dlq[0][1] and dlq[0][2] == 4


def test_simpan_dlq_ke_db(conn):
    a = amplop()
    k.simpan_dlq(conn, a, "TimeoutError: lambat", 4)
    baris = conn.execute("SELECT event_id, galat, percobaan, amplop->>'event_type' FROM event_dlq").fetchall()
    assert baris == [("evt_20261021_000001", "TimeoutError: lambat", 4, "resep.dimasak")]
