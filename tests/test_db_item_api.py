"""Integration tests for raw_jps_item_api upsert."""
from __future__ import annotations

import pytest

from nosuri import db


@pytest.fixture
def seeded(pg_conn):
    """Seed a parent row in raw_jps_shiseki so the FK is satisfied."""
    with pg_conn.cursor() as cur:
        cur.execute("DELETE FROM raw_jps_item_api WHERE subject_uri LIKE 'test:%'")
        cur.execute("DELETE FROM raw_jps_shiseki WHERE subject_uri LIKE 'test:%'")
        cur.execute(
            "INSERT INTO raw_jps_shiseki (subject_uri, jps_type, name, raw) "
            "VALUES (%s, '史跡', 'parent', '{}'::jsonb)",
            ("test:s1",),
        )
        cur.execute(
            "INSERT INTO raw_jps_shiseki (subject_uri, jps_type, name, raw) "
            "VALUES (%s, '史跡', 'parent2', '{}'::jsonb)",
            ("test:s2",),
        )
    yield pg_conn


def _row(subject="test:s1", **kw):
    base = {
        "subject_uri": subject,
        "lat": 35.0,
        "lon": 139.0,
        "link_url": "https://example.com/item",
        "description": "desc",
        "contents_rights_type": "cc-by",
        "raw": {"id": subject},
    }
    base.update(kw)
    return base


def _fetch(conn, subject):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ST_X(geom), ST_Y(geom), link_url, description, "
            "contents_rights_type, raw, fetched_at "
            "FROM raw_jps_item_api WHERE subject_uri = %s",
            (subject,),
        )
        return cur.fetchone()


def test_upsert_item_inserts_geometry(seeded):
    conn = seeded
    n = db.upsert_item_rows(conn, [_row(lat=35.5, lon=139.7)])
    assert n == 1
    row = _fetch(conn, "test:s1")
    assert row is not None
    x, y, link, desc, rights, raw, fetched_at = row
    assert x == pytest.approx(139.7)
    assert y == pytest.approx(35.5)
    assert link == "https://example.com/item"
    assert desc == "desc"
    assert rights == "cc-by"


def test_upsert_item_handles_null_geom(seeded):
    conn = seeded
    db.upsert_item_rows(conn, [_row(lat=None, lon=None)])
    with conn.cursor() as cur:
        cur.execute(
            "SELECT geom FROM raw_jps_item_api WHERE subject_uri = 'test:s1'"
        )
        (geom,) = cur.fetchone()
    assert geom is None


def test_upsert_item_updates_on_conflict(seeded):
    conn = seeded
    db.upsert_item_rows(conn, [_row(lat=35.0, lon=139.0, description="old")])
    db.upsert_item_rows(conn, [_row(lat=35.5, lon=139.7, description="new")])
    row = _fetch(conn, "test:s1")
    x, y, _, desc, *_ = row
    assert (x, y) == (pytest.approx(139.7), pytest.approx(35.5))
    assert desc == "new"


def test_upsert_item_batches_multiple(seeded):
    conn = seeded
    rows = [_row(subject="test:s1", lat=35.0, lon=139.0),
            _row(subject="test:s2", lat=34.0, lon=135.0)]
    n = db.upsert_item_rows(conn, rows)
    assert n == 2
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM raw_jps_item_api WHERE subject_uri LIKE 'test:%'"
        )
        assert cur.fetchone()[0] == 2


def test_upsert_item_empty_noop(seeded):
    assert db.upsert_item_rows(seeded, []) == 0
