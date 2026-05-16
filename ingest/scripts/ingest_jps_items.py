"""Enrich raw_jps_shiseki rows by calling JPS `/api/item/{id}` and upserting
the precise coordinates + linkUrl + description into raw_jps_item_api.

Usage:
    uv run python scripts/ingest_jps_items.py                    # all missing
    uv run python scripts/ingest_jps_items.py --limit 10         # smoke test
    uv run python scripts/ingest_jps_items.py --refresh          # re-fetch all
    uv run python scripts/ingest_jps_items.py --sleep 0.2
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingest import db, jps_item  # noqa: E402


BATCH_SIZE = 200


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=None, help="Cap the number of subjects to enrich.")
    p.add_argument("--sleep", type=float, default=0.3, help="Seconds between API calls (default: %(default)s).")
    p.add_argument("--refresh", action="store_true", help="Re-fetch even subjects already present in raw_jps_item_api.")
    p.add_argument("--commit-every", type=int, default=BATCH_SIZE, help="Commit every N rows (default: %(default)s).")
    return p.parse_args(argv)


def load_subject_uris(conn, *, refresh: bool, limit: int | None) -> list[str]:
    """Load all target subject_uris up front — commit() invalidates server-side cursors."""
    if refresh:
        sql = "SELECT subject_uri FROM raw_jps_shiseki ORDER BY subject_uri"
    else:
        sql = (
            "SELECT s.subject_uri FROM raw_jps_shiseki s "
            "LEFT JOIN raw_jps_item_api a USING (subject_uri) "
            "WHERE a.subject_uri IS NULL "
            "ORDER BY s.subject_uri"
        )
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    with conn.cursor() as cur:
        cur.execute(sql)
        return [r[0] for r in cur.fetchall()]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("ingest_jps_items")

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        log.error("DATABASE_URL is not set")
        return 2

    conn = psycopg2.connect(db_url)
    started = time.monotonic()
    fetched = with_coords = errors = 0
    buf: list[dict] = []
    try:
        subjects = load_subject_uris(conn, refresh=args.refresh, limit=args.limit)
        log.info("targets: %d subject_uris", len(subjects))
        for subject_uri in subjects:
            item_id = jps_item.subject_uri_to_item_id(subject_uri)
            try:
                resp = jps_item.fetch_item(item_id)
            except Exception as e:
                errors += 1
                log.warning("fetch failed for %s: %s", item_id, e)
                time.sleep(args.sleep)
                continue
            if resp is None:
                errors += 1
                log.warning("404 for %s", item_id)
                time.sleep(args.sleep)
                continue
            row = jps_item.parse_item(resp, subject_uri=subject_uri)
            buf.append(row)
            fetched += 1
            if row["lat"] is not None:
                with_coords += 1
            if len(buf) >= args.commit_every:
                db.upsert_item_rows(conn, buf)
                conn.commit()
                log.info("flushed %d rows (total fetched=%d with_coords=%d errors=%d)",
                         len(buf), fetched, with_coords, errors)
                buf.clear()
            time.sleep(args.sleep)
        if buf:
            db.upsert_item_rows(conn, buf)
            conn.commit()
            log.info("final flush %d rows", len(buf))
    finally:
        conn.close()

    elapsed = time.monotonic() - started
    log.info("done — fetched=%d with_coords=%d errors=%d in %.1fs",
             fetched, with_coords, errors, elapsed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
