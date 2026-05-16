"""Database helpers for upserting JPS records into raw tables."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import psycopg2.extras


_INSERT_SQL = """
INSERT INTO raw_jps_shiseki
    (subject_uri, jps_type, name, spatial_uri, geohash_uri,
     temporal, image_url, link_url, source_info, raw, fetched_at)
VALUES %s
ON CONFLICT (subject_uri) DO UPDATE SET
    jps_type    = EXCLUDED.jps_type,
    name        = EXCLUDED.name,
    spatial_uri = EXCLUDED.spatial_uri,
    geohash_uri = EXCLUDED.geohash_uri,
    temporal    = EXCLUDED.temporal,
    image_url   = EXCLUDED.image_url,
    link_url    = EXCLUDED.link_url,
    source_info = EXCLUDED.source_info,
    raw         = EXCLUDED.raw,
    fetched_at  = EXCLUDED.fetched_at
"""

_TEMPLATE = "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())"

_ITEM_INSERT_SQL = """
INSERT INTO raw_jps_item_api
    (subject_uri, geom, link_url, description, contents_rights_type, raw, fetched_at)
VALUES %s
ON CONFLICT (subject_uri) DO UPDATE SET
    geom                 = EXCLUDED.geom,
    link_url             = EXCLUDED.link_url,
    description          = EXCLUDED.description,
    contents_rights_type = EXCLUDED.contents_rights_type,
    raw                  = EXCLUDED.raw,
    fetched_at           = EXCLUDED.fetched_at
"""

_ITEM_TEMPLATE = (
    "(%s, "
    "CASE WHEN %s IS NULL OR %s IS NULL THEN NULL "
    "ELSE ST_SetSRID(ST_MakePoint(%s, %s), 4326) END, "
    "%s, %s, %s, %s, now())"
)


def _as_jsonb(value: Any) -> psycopg2.extras.Json | None:
    return psycopg2.extras.Json(value) if value is not None else None


def upsert_rows(conn, rows: Iterable[dict[str, Any]]) -> int:
    """UPSERT a batch of rows into raw_jps_shiseki. Returns count submitted.

    The caller controls the transaction (commit/rollback).
    """
    rows = list(rows)
    if not rows:
        return 0

    values = [
        (
            r["subject_uri"],
            r["jps_type"],
            r["name"],
            r.get("spatial_uri"),
            r.get("geohash_uri"),
            r.get("temporal"),
            r.get("image_url"),
            r.get("link_url"),
            _as_jsonb(r.get("source_info")),
            _as_jsonb(r["raw"]),
        )
        for r in rows
    ]
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, _INSERT_SQL, values, template=_TEMPLATE)
    return len(rows)


def upsert_item_rows(conn, rows: Iterable[dict[str, Any]]) -> int:
    """UPSERT a batch of rows into raw_jps_item_api. Returns count submitted.

    `lat`/`lon` may be None — geom is set to NULL in that case.
    """
    rows = list(rows)
    if not rows:
        return 0
    values = [
        (
            r["subject_uri"],
            r.get("lat"),
            r.get("lon"),
            r.get("lon"),
            r.get("lat"),
            r.get("link_url"),
            r.get("description"),
            r.get("contents_rights_type"),
            _as_jsonb(r["raw"]),
        )
        for r in rows
    ]
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur, _ITEM_INSERT_SQL, values, template=_ITEM_TEMPLATE
        )
    return len(rows)
