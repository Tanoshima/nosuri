"""Fetch JPS historic-site records via SPARQL and upsert into raw_jps_shiseki.

Usage:
    uv run python scripts/ingest_jps_shiseki.py             # all default types
    uv run python scripts/ingest_jps_shiseki.py --limit 20  # smoke test
    uv run python scripts/ingest_jps_shiseki.py --types 史跡 名勝
    uv run python scripts/ingest_jps_shiseki.py --dry-run
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from itertools import islice

import psycopg2

# Ensure the repo root is on sys.path when invoked as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingest import db, jps  # noqa: E402


DEFAULT_TYPES = ["史跡", "史跡名勝天然記念物等", "名勝", "天然記念物"]
BATCH_SIZE = 500


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--types",
        nargs="+",
        default=DEFAULT_TYPES,
        help=f"JPS type names to ingest (default: {' '.join(DEFAULT_TYPES)})",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after this many rows per type (for smoke tests).",
    )
    p.add_argument(
        "--page-size",
        type=int,
        default=jps.DEFAULT_PAGE_SIZE,
        help="SPARQL LIMIT per page (default: %(default)s).",
    )
    p.add_argument(
        "--sleep",
        type=float,
        default=1.0,
        help="Seconds to wait between paginated SPARQL calls (default: 1.0).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse but do not write to the DB.",
    )
    return p.parse_args(argv)


def chunked(it, n):
    it = iter(it)
    while True:
        batch = list(islice(it, n))
        if not batch:
            return
        yield batch


def ingest_type(conn, jps_type: str, *, page_size: int, sleep: float,
                limit: int | None, dry_run: bool, log: logging.Logger) -> int:
    log.info("→ fetching type:%s (page_size=%d)", jps_type, page_size)
    rows_iter = jps.iter_rows(
        jps_type=jps_type, page_size=page_size, sleep_between=sleep
    )
    if limit is not None:
        rows_iter = islice(rows_iter, limit)

    total = 0
    for batch in chunked(rows_iter, BATCH_SIZE):
        if dry_run:
            log.info("[dry-run] would upsert %d rows", len(batch))
        else:
            db.upsert_rows(conn, batch)
            conn.commit()
        total += len(batch)
        log.info("  upserted %d rows (running total for type: %d)", len(batch), total)
    log.info("✓ type:%s done — %d rows", jps_type, total)
    return total


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    log = logging.getLogger("ingest_jps_shiseki")

    db_url = os.environ.get("DATABASE_URL")
    if not db_url and not args.dry_run:
        log.error("DATABASE_URL is not set")
        return 2

    conn = None if args.dry_run else psycopg2.connect(db_url)
    started = time.monotonic()
    grand_total = 0
    try:
        for t in args.types:
            grand_total += ingest_type(
                conn,
                t,
                page_size=args.page_size,
                sleep=args.sleep,
                limit=args.limit,
                dry_run=args.dry_run,
                log=log,
            )
    finally:
        if conn is not None:
            conn.close()
    log.info(
        "done — %d rows across %d types in %.1fs",
        grand_total,
        len(args.types),
        time.monotonic() - started,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
