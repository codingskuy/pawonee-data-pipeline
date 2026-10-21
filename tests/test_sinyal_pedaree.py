import json
from datetime import datetime, timedelta, timezone

import pytest

from sinyal_pedaree import (
    VERSI_KONTRAK,
    awal_slot,
    bangun_sinyal,
    periode_terakhir_selesai,
    terbitkan_periode,
)

UTC = timezone.utc
T0 = datetime(2026, 10, 21, 10, 15, tzinfo=UTC)


def test_awal_slot_membulatkan_ke_bawah_15_menit():
    assert awal_slot(datetime(2026, 10, 21, 10, 29, 59, tzinfo=UTC)) == T0
    assert awal_slot(datetime(2026, 10, 21, 17, 30, tzinfo=timezone(timedelta(hours=7)))) == datetime(
        2026, 10, 21, 10, 30, tzinfo=UTC
    )


def test_awal_slot_menolak_waktu_tanpa_zona():
    with pytest.raises(ValueError):
        awal_slot(datetime(2026, 10, 21, 10, 0))


def test_periode_terakhir_selesai_adalah_slot_sebelumnya():
    mulai, selesai = periode_terakhir_selesai(datetime(2026, 10, 21, 10, 31, tzinfo=UTC))
    assert (mulai, selesai) == (T0, datetime(2026, 10, 21, 10, 30, tzinfo=UTC))


def test_bangun_sinyal_membawa_keluarga_waktu_dan_versi():
    s = bangun_sinyal(
        "KEL-0001",
        T0,
        [{"resep_id": "R-06", "jiwa": 4, "gram_g2_terserap": 400, "tanggal": "2026-10-21"}],
    )
    assert s["keluarga_id"] == "KEL-0001"
    assert s["versi_kontrak"] == VERSI_KONTRAK == "v1"
    assert s["topik"] == "sinyal.pedaree.v1"
    assert s["periode_mulai"] == "2026-10-21T10:15:00Z"
    assert s["periode_selesai"] == "2026-10-21T10:30:00Z"
    assert s["gram_g2_terserap_total"] == 400


def test_bangun_sinyal_tanda_ganda_resep_dan_hari_sama_dihitung_sekali():
    b = {"resep_id": "R-06", "jiwa": 4, "gram_g2_terserap": 400, "tanggal": "2026-10-21"}
    s = bangun_sinyal("KEL-0001", T0, [b, dict(b), {**b, "resep_id": "R-02", "gram_g2_terserap": 100}])
    assert s["gram_g2_terserap_total"] == 500
    assert [r["resep_id"] for r in s["resep_dimasak"]] == ["R-06", "R-02"]


def _masak(conn, keluarga, resep, gram, waktu, tanggal="2026-10-21"):
    conn.execute(
        "INSERT INTO riwayat_masak (keluarga_id, resep_id, jiwa, gram_g2_terserap, tanggal, dibuat_pada)"
        " VALUES (%s,%s,4,%s,%s,%s)",
        (keluarga, resep, gram, tanggal, waktu),
    )


def test_terbitkan_menulis_satu_sinyal_per_keluarga_dalam_slot(conn):
    _masak(conn, "KEL-0001", "R-06", 400, T0 + timedelta(minutes=1))
    _masak(conn, "KEL-0002", "R-02", 250, T0 + timedelta(minutes=14))
    _masak(conn, "KEL-0003", "R-01", 999, T0 + timedelta(minutes=15))  # slot berikutnya
    _masak(conn, "KEL-0004", "R-01", 999, T0 - timedelta(seconds=1))  # slot sebelumnya
    assert terbitkan_periode(conn, T0) == 2
    baris = conn.execute(
        "SELECT keluarga_id, schema_version, topik, event_id, muatan FROM sinyal_pedaree ORDER BY keluarga_id"
    ).fetchall()
    assert [b[0] for b in baris] == ["KEL-0001", "KEL-0002"]
    assert {b[1] for b in baris} == {"v1"}
    assert {b[2] for b in baris} == {"sinyal.pedaree.v1"}
    assert all(b[3].startswith("evt_20261021_") and len(b[3]) == 19 for b in baris)
    assert baris[0][4]["gram_g2_terserap_total"] == 400


def test_terbitkan_ulang_periode_sama_tidak_menggandakan(conn):
    _masak(conn, "KEL-0001", "R-06", 400, T0 + timedelta(minutes=1))
    assert terbitkan_periode(conn, T0) == 1
    assert terbitkan_periode(conn, T0) == 0
    assert conn.execute("SELECT count(*) FROM sinyal_pedaree").fetchone()[0] == 1


def test_kegagalan_tulis_membatalkan_seluruh_periode_lalu_ulang_aman(conn, monkeypatch):
    import sinyal_pedaree as m

    _masak(conn, "KEL-0001", "R-06", 400, T0 + timedelta(minutes=1))
    _masak(conn, "KEL-0002", "R-02", 250, T0 + timedelta(minutes=2))
    asli = m.bangun_sinyal
    panggilan = {"n": 0}

    def rusak(*a, **k):
        panggilan["n"] += 1
        if panggilan["n"] == 2:
            raise RuntimeError("gagal di tengah")
        return asli(*a, **k)

    monkeypatch.setattr(m, "bangun_sinyal", rusak)
    with pytest.raises(RuntimeError):
        terbitkan_periode(conn, T0)
    assert conn.execute("SELECT count(*) FROM sinyal_pedaree").fetchone()[0] == 0
    monkeypatch.setattr(m, "bangun_sinyal", asli)
    assert terbitkan_periode(conn, T0) == 2
    assert terbitkan_periode(conn, T0) == 0


def test_slot_kosong_tidak_menulis_apa_pun(conn):
    assert terbitkan_periode(conn, T0) == 0


def test_constraint_menolak_duplikat_langsung(conn):
    import psycopg

    _masak(conn, "KEL-0001", "R-06", 400, T0 + timedelta(minutes=1))
    terbitkan_periode(conn, T0)
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(
            "INSERT INTO sinyal_pedaree (event_id, keluarga_id, periode_mulai, periode_selesai, muatan)"
            " VALUES ('evt_x', 'KEL-0001', %s, %s, %s::jsonb)",
            (T0, T0 + timedelta(minutes=15), json.dumps({})),
        )


def test_pipeline_sekali_lewat_cli(conn, pg_url, monkeypatch, capsys):
    import pipeline

    _masak(conn, "KEL-0001", "R-06", 400, T0 + timedelta(minutes=1))
    monkeypatch.setenv("DATABASE_URL", pg_url)
    assert pipeline.main(["--sekali", "--sekarang", "2026-10-21T10:31:00+00:00"]) == 0
    assert "1 sinyal baru" in capsys.readouterr().out
    assert pipeline.main(["--sekali", "--sekarang", "2026-10-21T10:44:00+00:00"]) == 0
    assert "0 sinyal baru" in capsys.readouterr().out


def test_pipeline_tanpa_database_url_gagal_jelas(monkeypatch):
    import pipeline

    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert pipeline.main(["--sekali"]) == 2
