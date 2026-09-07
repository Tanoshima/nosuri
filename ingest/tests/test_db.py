"""Integration tests for raw_jps_shiseki upsert."""
from __future__ import annotations

import pytest

from ingest import db


@pytest.fixture
def clean_table(pg_conn):
    """Empty the table at the start of the test (rolled back by pg_conn)."""
    with pg_conn.cursor() as cur:
        cur.execute("DELETE FROM raw_jps_shiseki")
    yield pg_conn


COLUMNS = [
    "subject_uri", "jps_type", "name", "spatial_uris", "geohash_uris",
    "temporals", "image_urls", "source_infos", "raw", "fetched_at",
]


def _row(subject: str, **overrides):
    base = {
        "subject_uri": subject,
        "jps_type": "史跡",
        "name": "テスト史跡",
        "spatial_uris": [],
        "geohash_uris": [],
        "temporals": [],
        "image_urls": [],
        "source_infos": [],
        "raw": [{"s": {"type": "uri", "value": subject}}],
    }
    base.update(overrides)
    return base


def _fetch(conn, subject: str, jps_type: str = "史跡") -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {', '.join(COLUMNS)} FROM raw_jps_shiseki "
            "WHERE subject_uri = %s AND jps_type = %s",
            (subject, jps_type),
        )
        row = cur.fetchone()
    return None if row is None else dict(zip(COLUMNS, row))


def test_upsert_inserts_new_row(clean_table):
    conn = clean_table
    n = db.upsert_rows(conn, [_row("uri:1", name="小田城跡")])
    assert n == 1
    got = _fetch(conn, "uri:1")
    assert got is not None
    assert got["name"] == "小田城跡"
    assert got["jps_type"] == "史跡"
    assert got["raw"] == [{"s": {"type": "uri", "value": "uri:1"}}]


def test_upsert_updates_on_conflict(clean_table):
    conn = clean_table
    db.upsert_rows(conn, [_row("uri:1", name="旧名")])
    before = _fetch(conn, "uri:1")

    db.upsert_rows(conn, [_row("uri:1", name="新名", temporals=["鎌倉時代"])])
    after = _fetch(conn, "uri:1")

    assert after["name"] == "新名"
    assert after["temporals"] == ["鎌倉時代"]
    assert after["fetched_at"] >= before["fetched_at"]


def test_same_subject_under_two_types_keeps_both_rows(clean_table):
    """A subject published as both 史跡 and 名勝 must not overwrite itself."""
    conn = clean_table
    db.upsert_rows(conn, [_row("uri:1", jps_type="史跡", temporals=["鎌倉時代"])])
    db.upsert_rows(conn, [_row("uri:1", jps_type="名勝", temporals=["江戸時代"])])

    assert _fetch(conn, "uri:1", "史跡")["temporals"] == ["鎌倉時代"]
    assert _fetch(conn, "uri:1", "名勝")["temporals"] == ["江戸時代"]


def test_upsert_stores_multi_valued_predicates(clean_table):
    conn = clean_table
    db.upsert_rows(
        conn,
        [
            _row(
                "uri:1",
                spatial_uris=["place:1", "place:2"],
                image_urls=["img:1"],
                source_infos=["https://example.com/src"],
            )
        ],
    )
    got = _fetch(conn, "uri:1")
    assert got["spatial_uris"] == ["place:1", "place:2"]
    assert got["image_urls"] == ["img:1"]
    assert got["source_infos"] == ["https://example.com/src"]


def test_upsert_merges_duplicate_keys_within_a_batch(clean_table):
    """A batch may not touch the same key twice — duplicates are merged first."""
    conn = clean_table
    rows = [
        _row("uri:1", spatial_uris=["place:1"]),
        _row("uri:1", spatial_uris=["place:2"]),
    ]
    n = db.upsert_rows(conn, rows)
    assert n == 1
    assert _fetch(conn, "uri:1")["spatial_uris"] == ["place:1", "place:2"]
    # the caller's rows are left untouched
    assert rows[0]["spatial_uris"] == ["place:1"]


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


def test_upsert_preserves_raw_jsonb_structure(clean_table):
    conn = clean_table
    raw = [
        {
            "s": {"type": "uri", "value": "uri:1"},
            "name": {"type": "literal", "value": "X"},
            "extra": {"nested": [1, 2, 3]},
        },
        {"s": {"type": "uri", "value": "uri:1"}},
    ]
    db.upsert_rows(conn, [_row("uri:1", raw=raw)])
    got = _fetch(conn, "uri:1")
    assert got["raw"] == raw
