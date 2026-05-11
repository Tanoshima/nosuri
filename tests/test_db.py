"""Integration tests for raw_jps_shiseki upsert."""
from __future__ import annotations

import json

import pytest

from nosuri import db


@pytest.fixture
def clean_table(pg_conn):
    """Empty the table at the start of the test (rolled back by pg_conn)."""
    with pg_conn.cursor() as cur:
        cur.execute("DELETE FROM raw_jps_shiseki")
    yield pg_conn


def _row(subject: str, **overrides):
    base = {
        "subject_uri": subject,
        "jps_type": "史跡",
        "name": "テスト史跡",
        "spatial_uri": None,
        "geohash_uri": None,
        "temporal": None,
        "image_url": None,
        "source_info": None,
        "raw": {"s": {"type": "uri", "value": subject}},
    }
    base.update(overrides)
    return base


def _fetch(conn, subject: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT subject_uri, jps_type, name, spatial_uri, geohash_uri, "
            "temporal, image_url, source_info, raw, fetched_at "
            "FROM raw_jps_shiseki WHERE subject_uri = %s",
            (subject,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    cols = [
        "subject_uri", "jps_type", "name", "spatial_uri", "geohash_uri",
        "temporal", "image_url", "source_info", "raw", "fetched_at",
    ]
    return dict(zip(cols, row))


def test_upsert_inserts_new_row(clean_table):
    conn = clean_table
    n = db.upsert_rows(conn, [_row("uri:1", name="小田城跡")])
    assert n == 1
    got = _fetch(conn, "uri:1")
    assert got is not None
    assert got["name"] == "小田城跡"
    assert got["jps_type"] == "史跡"
    assert got["raw"] == {"s": {"type": "uri", "value": "uri:1"}}


def test_upsert_updates_on_conflict(clean_table):
    conn = clean_table
    db.upsert_rows(conn, [_row("uri:1", name="旧名")])
    before = _fetch(conn, "uri:1")

    db.upsert_rows(conn, [_row("uri:1", name="新名", temporal="鎌倉時代")])
    after = _fetch(conn, "uri:1")

    assert after["name"] == "新名"
    assert after["temporal"] == "鎌倉時代"
    assert after["fetched_at"] >= before["fetched_at"]


def test_upsert_batches_multiple_rows(clean_table):
    conn = clean_table
    rows = [_row(f"uri:{i}", name=f"史跡{i}") for i in range(5)]
    n = db.upsert_rows(conn, rows)
    assert n == 5
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM raw_jps_shiseki")
        assert cur.fetchone()[0] == 5


def test_upsert_empty_is_noop(clean_table):
    conn = clean_table
    n = db.upsert_rows(conn, [])
    assert n == 0


def test_upsert_stores_source_info_as_text(clean_table):
    """source_info column is jsonb; we store the URI as a JSON string."""
    conn = clean_table
    db.upsert_rows(
        conn,
        [_row("uri:1", source_info="https://example.com/src")],
    )
    got = _fetch(conn, "uri:1")
    assert got["source_info"] == "https://example.com/src"


def test_upsert_preserves_raw_jsonb_structure(clean_table):
    conn = clean_table
    raw = {
        "s": {"type": "uri", "value": "uri:1"},
        "name": {"type": "literal", "value": "X"},
        "extra": {"nested": [1, 2, 3]},
    }
    db.upsert_rows(conn, [_row("uri:1", raw=raw)])
    got = _fetch(conn, "uri:1")
    assert got["raw"] == raw
