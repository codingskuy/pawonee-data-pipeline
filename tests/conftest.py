"""Fixture bersama. Uji DB memakai klaster Postgres sementara (initdb), dilewati bila tak ada."""

import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

# DDL sumber HANYA untuk uji: tabel ini milik pawonee-backend-service (asumsi kolom, lihat ADR-0002).
DDL_SUMBER_UJI = """
CREATE TABLE riwayat_masak (
    id BIGSERIAL PRIMARY KEY,
    keluarga_id TEXT NOT NULL,
    resep_id TEXT NOT NULL,
    jiwa INT NOT NULL,
    gram_g2_terserap INT NOT NULL,
    tanggal DATE NOT NULL,
    dibuat_pada TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _port_bebas() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def pg_url(tmp_path_factory):
    initdb = shutil.which("initdb")
    pg_ctl = shutil.which("pg_ctl")
    if not (initdb and pg_ctl):
        pytest.skip("Postgres lokal (initdb/pg_ctl) tidak tersedia")
    pytest.importorskip("psycopg")
    data = tmp_path_factory.mktemp("pgdata")
    port = _port_bebas()
    subprocess.run([initdb, "-D", str(data), "-U", "uji", "-A", "trust", "-E", "UTF8"],
                   check=True, capture_output=True)
    subprocess.run(
        [pg_ctl, "-D", str(data), "-w", "-o", f"-p {port} -c listen_addresses=127.0.0.1 -c fsync=off "
         "-c unix_socket_directories=''", "-l", str(data / "log"), "start"],
        check=True, capture_output=True)
    yield f"postgresql://uji@127.0.0.1:{port}/postgres"
    subprocess.run([pg_ctl, "-D", str(data), "-m", "immediate", "stop"], capture_output=True)


@pytest.fixture()
def conn(pg_url):
    import psycopg

    with psycopg.connect(pg_url, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        c.execute(DDL_SUMBER_UJI)
        for f in sorted(SRC.glob("skema*.sql")):
            c.execute(f.read_text())
        yield c
