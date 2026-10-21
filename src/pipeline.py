"""Orkestrasi pipa Pawonee. Dijalankan scheduler (`config/pipeline.yaml`, tiap 15 menit)."""

import argparse
import os
import sys
from datetime import date, datetime, timezone

import psycopg

from serapan_mingguan import hitung_minggu, minggu_terakhir_selesai
from sinyal_pedaree import periode_terakhir_selesai, terbitkan_periode


def jalankan_sinyal(database_url: str, sekarang: datetime) -> tuple[datetime, int]:
    mulai, _ = periode_terakhir_selesai(sekarang)
    with psycopg.connect(database_url) as conn:
        return mulai, terbitkan_periode(conn, mulai)


def jalankan_serapan(database_url: str, senin: date) -> dict:
    with psycopg.connect(database_url) as conn:
        return hitung_minggu(conn, senin)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Pipa data Pawonee")
    p.add_argument("--sekali", action="store_true", help="jalankan satu siklus lalu keluar")
    p.add_argument("--sekarang", help="waktu acuan RFC3339 (uji/backfill); default: sekarang UTC")
    p.add_argument("--serapan-mingguan", action="store_true",
                   help="hitung agregat serapan mingguan (default: minggu WIB terakhir yang tertutup)")
    p.add_argument("--minggu", help="Senin (YYYY-MM-DD) minggu yang dihitung; bersama --serapan-mingguan")
    args = p.parse_args(argv)

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL belum diatur", file=sys.stderr)
        return 2
    sekarang = datetime.fromisoformat(args.sekarang) if args.sekarang else datetime.now(timezone.utc)
    if args.serapan_mingguan:
        senin = date.fromisoformat(args.minggu) if args.minggu else minggu_terakhir_selesai(sekarang)
        try:
            if senin > minggu_terakhir_selesai(sekarang):
                raise ValueError(f"minggu {senin} belum tertutup (Minggu 23.59 WIB)")
            ringkas = jalankan_serapan(url, senin)
        except ValueError as e:
            print(f"galat: {e}", file=sys.stderr)
            return 2
        print(f"serapan mingguan {senin}: {ringkas['jumlah_keluarga_diukur']} keluarga diukur, "
              f"{ringkas['serapan_g']} g, hemat Rp{ringkas['nilai_hemat_rp']}")
        return 0
    mulai, baru = jalankan_sinyal(url, sekarang)
    print(f"sinyal.pedaree.v1 periode {mulai.isoformat()}: {baru} sinyal baru")
    return 0


if __name__ == "__main__":
    sys.exit(main())
