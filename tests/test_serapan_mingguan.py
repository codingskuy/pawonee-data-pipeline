from datetime import date, datetime, timedelta, timezone

import pytest

import serapan_mingguan as s

UTC = timezone.utc
SENIN = date(2026, 10, 19)  # Senin
LAMA = datetime(2026, 9, 1, tzinfo=UTC)  # terdaftar jauh sebelum minggu uji


def masak(resep, gram, tanggal="2026-10-19"):
    return {"resep_id": resep, "gram_g2_terserap": gram, "tanggal": tanggal}


def busuk(gram, grade="G2-V"):
    return {"nama_bahan": "kangkung", "gram": gram, "kode_grade": grade}


# ---- periode WIB ----
def test_batas_minggu_senin_0000_sampai_minggu_2359_wib():
    awal, akhir = s.batas_minggu_wib(SENIN)
    assert awal.isoformat() == "2026-10-19T00:00:00+07:00"
    assert akhir - timedelta(seconds=1) == datetime(2026, 10, 25, 23, 59, 59, tzinfo=s.WIB)


def test_batas_minggu_menolak_bukan_senin():
    with pytest.raises(ValueError):
        s.batas_minggu_wib(date(2026, 10, 20))


def test_senin_dari_dan_minggu_terakhir_selesai():
    assert s.senin_dari(date(2026, 10, 25)) == SENIN  # Minggu
    assert s.senin_dari(SENIN) == SENIN
    # Minggu 23.59 WIB = 16.59 UTC -> minggu itu belum tertutup
    assert s.minggu_terakhir_selesai(datetime(2026, 10, 25, 16, 59, tzinfo=UTC)) == date(2026, 10, 12)
    # Senin 00.00 WIB = Minggu 17.00 UTC -> minggu 19 Okt sudah tertutup
    assert s.minggu_terakhir_selesai(datetime(2026, 10, 25, 17, 0, tzinfo=UTC)) == SENIN


def test_keluarga_baru_diukur_mulai_minggu_kedua():
    daftar = datetime(2026, 10, 21, 3, 0, tzinfo=UTC)  # Rabu minggu 19 Okt
    assert s.keluarga_diukur(daftar, SENIN) is False
    assert s.keluarga_diukur(daftar, SENIN + timedelta(days=7)) is True
    # Minggu 23.30 WIB (16.30 UTC) masih minggu 19 Okt; Senin 00.10 WIB (Minggu 17.10 UTC) sudah minggu berikutnya
    assert s.keluarga_diukur(datetime(2026, 10, 25, 16, 30, tzinfo=UTC), SENIN + timedelta(days=7)) is True
    assert s.keluarga_diukur(datetime(2026, 10, 25, 17, 10, tzinfo=UTC), SENIN + timedelta(days=7)) is False


# ---- rumus ----
def test_nilai_hemat_gram_x_harga_x_0_6_integer():
    assert s.nilai_hemat(1_500) == 90_000
    assert s.nilai_hemat(150_000) == 9_000_000  # acuan program BRD 30
    assert s.nilai_hemat(1, 3) == 1  # floor(1,8)
    assert isinstance(s.nilai_hemat(333), int)


def test_rasio_basis_poin_dan_tanpa_data():
    assert s.rasio_bp(800, 200) == 8_000
    assert s.rasio_bp(799, 201) == 7_990
    assert s.rasio_bp(0, 0) is None
    assert s.rasio_bp(0, 50) == 0


@pytest.mark.parametrize(
    "serapan,ok",
    [(1_499, False), (1_500, True), (1_501, True)],
)
def test_ambang_serapan_1500(serapan, ok):
    assert s.hitung_keluarga([masak("R-01", serapan)], [])["memenuhi_serapan"] is ok


@pytest.mark.parametrize("waste,ok", [(299, True), (300, True), (301, False)])
def test_ambang_waste_300(waste, ok):
    assert s.hitung_keluarga([], [busuk(waste)])["memenuhi_waste"] is ok


@pytest.mark.parametrize("serapan,waste,ok", [(800, 200, True), (799, 201, False), (1000, 0, True)])
def test_ambang_rasio_80_persen(serapan, waste, ok):
    h = s.hitung_keluarga([masak("R-01", serapan)], [busuk(waste)] if waste else [])
    assert h["memenuhi_rasio"] is ok


def test_rasio_null_bila_tak_ada_data_dan_flag_null():
    h = s.hitung_keluarga([], [])
    assert h["rasio_bp"] is None and h["memenuhi_rasio"] is None
    assert h["serapan_g"] == 0 and h["memenuhi_serapan"] is False and h["memenuhi_waste"] is True


def test_tanda_ganda_resep_dan_hari_sama_dihitung_sekali():
    h = s.hitung_keluarga(
        [masak("R-06", 400), masak("R-06", 400), masak("R-06", 400, "2026-10-20"), masak("R-02", 100)], []
    )
    assert h["serapan_g"] == 900  # R-06 hari1 + R-06 hari2 + R-02


def test_busuk_non_g2_tidak_dihitung_waste():
    h = s.hitung_keluarga([masak("R-01", 1000)], [busuk(500, "NON-G2"), busuk(100, "G2-U")])
    assert h["waste_dapur_g"] == 100


def test_agregat_program_target_150kg_dan_9_juta():
    sehat = {"serapan_g": 1_500, "waste_dapur_g": 0, "nilai_hemat_rp": 90_000, "memenuhi_serapan": True,
             "memenuhi_rasio": True, "memenuhi_waste": True}
    p = s.hitung_program([sehat] * 100)
    assert p["jumlah_keluarga_diukur"] == 100
    assert p["serapan_g"] == 150_000 and p["nilai_hemat_rp"] == 9_000_000
    assert p["memenuhi_target_serapan"] and p["memenuhi_target_hemat"]
    p2 = s.hitung_program([sehat] * 99)
    assert not p2["memenuhi_target_serapan"] and not p2["memenuhi_target_hemat"]


# ---- DB ----
def _daftar(conn, keluarga, waktu=LAMA):
    conn.execute("INSERT INTO profil_keluarga (keluarga_id, dibuat_pada) VALUES (%s,%s)", (keluarga, waktu))


def _masak(conn, keluarga, resep, gram, tanggal="2026-10-19"):
    conn.execute(
        "INSERT INTO riwayat_masak (keluarga_id, resep_id, jiwa, gram_g2_terserap, tanggal) VALUES (%s,%s,4,%s,%s)",
        (keluarga, resep, gram, tanggal),
    )


def _busuk(conn, keluarga, gram, tanggal="2026-10-20", grade="G2-V"):
    conn.execute(
        "INSERT INTO laporan_busuk (keluarga_id, nama_bahan, gram, kode_grade, tanggal) VALUES (%s,'kangkung',%s,%s,%s)",
        (keluarga, gram, grade, tanggal),
    )


def test_hitung_minggu_menulis_per_keluarga_dan_program(conn):
    _daftar(conn, "KEL-0001")
    _daftar(conn, "KEL-0002")
    _daftar(conn, "KEL-0003", datetime(2026, 10, 21, tzinfo=UTC))  # minggu adaptasi -> tak diukur
    _masak(conn, "KEL-0001", "R-06", 1_000)
    _masak(conn, "KEL-0001", "R-06", 1_000)  # tanda ganda
    _masak(conn, "KEL-0001", "R-02", 700, "2026-10-25")  # Minggu 23.xx WIB masih dalam minggu
    _masak(conn, "KEL-0001", "R-02", 9_999, "2026-10-26")  # Senin berikutnya: di luar
    _busuk(conn, "KEL-0001", 200)
    _masak(conn, "KEL-0003", "R-01", 5_000)
    p = s.hitung_minggu(conn, SENIN)
    assert p["jumlah_keluarga_diukur"] == 2
    baris = conn.execute(
        "SELECT keluarga_id, serapan_g, waste_dapur_g, rasio_bp, nilai_hemat_rp, memenuhi_serapan,"
        " memenuhi_rasio, memenuhi_waste FROM agregat_serapan_mingguan ORDER BY keluarga_id"
    ).fetchall()
    assert baris == [
        ("KEL-0001", 1_700, 200, 8_947, 102_000, True, True, True),
        ("KEL-0002", 0, 0, None, 0, False, None, True),
    ]
    prog = conn.execute("SELECT serapan_g, waste_dapur_g, nilai_hemat_rp, jumlah_keluarga_diukur,"
                        " keluarga_memenuhi_serapan FROM agregat_serapan_program").fetchall()
    assert prog == [(1_700, 200, 102_000, 2, 1)]


def test_hitung_ulang_idempoten_dan_menimpa_data_terlambat(conn):
    _daftar(conn, "KEL-0001")
    _masak(conn, "KEL-0001", "R-06", 1_000)
    s.hitung_minggu(conn, SENIN)
    s.hitung_minggu(conn, SENIN)
    assert conn.execute("SELECT count(*) FROM agregat_serapan_mingguan").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM agregat_serapan_program").fetchone()[0] == 1
    _masak(conn, "KEL-0001", "R-02", 600)  # data terlambat
    s.hitung_minggu(conn, SENIN)
    assert conn.execute("SELECT serapan_g FROM agregat_serapan_mingguan").fetchone()[0] == 1_600


def test_hitung_minggu_menolak_bukan_senin(conn):
    with pytest.raises(ValueError):
        s.hitung_minggu(conn, date(2026, 10, 20))


def test_cli_serapan_mingguan(conn, pg_url, monkeypatch, capsys):
    import pipeline

    _daftar(conn, "KEL-0001")
    _masak(conn, "KEL-0001", "R-06", 1_500)
    monkeypatch.setenv("DATABASE_URL", pg_url)
    sekarang = "2026-10-26T01:00:00+07:00"
    assert pipeline.main(["--serapan-mingguan", "--sekarang", sekarang]) == 0
    assert "1 keluarga diukur, 1500 g, hemat Rp90000" in capsys.readouterr().out
    # minggu berjalan ditolak
    assert pipeline.main(["--serapan-mingguan", "--minggu", "2026-10-26", "--sekarang", sekarang]) == 2
