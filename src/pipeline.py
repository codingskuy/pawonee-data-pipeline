"""Orkestrasi pipa Pawonee. Dijalankan scheduler (`config/pipeline.yaml`, tiap 15 menit)."""

import argparse
import os
import sys
from datetime import datetime, timezone

import psycopg

from sinyal_pedaree import periode_terakhir_selesai, terbitkan_periode


def jalankan_sinyal(database_url: str, sekarang: datetime) -> tuple[datetime, int]:
    mulai, _ = periode_terakhir_selesai(sekarang)
    with psycopg.connect(database_url) as conn:
        return mulai, terbitkan_periode(conn, mulai)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Pipa data Pawonee")
    p.add_argument("--sekali", action="store_true", help="jalankan satu siklus lalu keluar")
    p.add_argument("--sekarang", help="waktu acuan RFC3339 (uji/backfill); default: sekarang UTC")
    args = p.parse_args(argv)

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL belum diatur", file=sys.stderr)
        return 2
    sekarang = datetime.fromisoformat(args.sekarang) if args.sekarang else datetime.now(timezone.utc)
    mulai, baru = jalankan_sinyal(url, sekarang)
    print(f"sinyal.pedaree.v1 periode {mulai.isoformat()}: {baru} sinyal baru")
    return 0


if __name__ == "__main__":
    sys.exit(main())
