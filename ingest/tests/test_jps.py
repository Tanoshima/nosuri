"""Tests for the JPS SPARQL fetcher/parser."""
from __future__ import annotations

import json

import pytest
import responses

from ingest import jps


SAMPLE_RESPONSE = {
    "head": {
        "vars": ["s", "name", "spatial", "geo", "temporal", "image", "source"],
    },
    "results": {
        "bindings": [
            {
                "s": {"type": "uri", "value": "https://jpsearch.go.jp/entity/x1"},
                "name": {"type": "literal", "value": "小田城跡"},
                "spatial": {
                    "type": "uri",
                    "value": "https://jpsearch.go.jp/entity/place/茨城県.つくば市",
                },
                "geo": {"type": "uri", "value": "http://geohash.org/xnd28"},
                "temporal": {"type": "literal", "value": "鎌倉時代"},
                "image": {"type": "uri", "value": "https://example.com/i.jpg"},
                "source": {"type": "uri", "value": "https://example.com/src"},
            },
            {
                "s": {"type": "uri", "value": "https://jpsearch.go.jp/entity/x2"},
                "name": {"type": "literal", "value": "登呂遺跡"},
            },
        ],
    },
}


def test_parse_bindings_extracts_all_fields():
    rows = jps.parse_bindings(SAMPLE_RESPONSE, jps_type="史跡")
    assert len(rows) == 2

    a = rows[0]
    assert a["subject_uri"] == "https://jpsearch.go.jp/entity/x1"
    assert a["jps_type"] == "史跡"
    assert a["name"] == "小田城跡"
    assert a["spatial_uris"] == ["https://jpsearch.go.jp/entity/place/茨城県.つくば市"]
    assert a["geohash_uris"] == ["http://geohash.org/xnd28"]
    assert a["temporals"] == ["鎌倉時代"]
    assert a["image_urls"] == ["https://example.com/i.jpg"]
    assert a["source_infos"] == ["https://example.com/src"]
    assert a["raw"] == [SAMPLE_RESPONSE["results"]["bindings"][0]]


def test_parse_bindings_missing_optionals_are_empty_arrays():
    rows = jps.parse_bindings(SAMPLE_RESPONSE, jps_type="史跡")
    b = rows[1]
    assert b["subject_uri"] == "https://jpsearch.go.jp/entity/x2"
    assert b["name"] == "登呂遺跡"
    assert b["spatial_uris"] == []
    assert b["geohash_uris"] == []
    assert b["temporals"] == []
    assert b["image_urls"] == []
    assert b["source_infos"] == []


def test_parse_bindings_empty():
    empty = {"head": {"vars": []}, "results": {"bindings": []}}
    assert jps.parse_bindings(empty, jps_type="史跡") == []


def test_parse_bindings_keeps_every_value_of_a_multi_valued_predicate():
    """Multiple bindings for the same subject collapse to one row, keeping all values."""
    data = {
        "head": {"vars": ["s", "name", "spatial"]},
        "results": {
            "bindings": [
                {
                    "s": {"type": "uri", "value": "uri:1"},
                    "name": {"type": "literal", "value": "A"},
                    "spatial": {"type": "uri", "value": "place:1"},
                },
                {
                    "s": {"type": "uri", "value": "uri:1"},
                    "name": {"type": "literal", "value": "A"},
                    "spatial": {"type": "uri", "value": "place:2"},
                },
            ]
        },
    }
    rows = jps.parse_bindings(data, jps_type="史跡")
    assert len(rows) == 1
    assert rows[0]["spatial_uris"] == ["place:1", "place:2"]
    assert len(rows[0]["raw"]) == 2


def test_parse_bindings_does_not_repeat_identical_values():
    data = {
        "head": {"vars": ["s", "name", "spatial", "image"]},
        "results": {
            "bindings": [
                {
                    "s": {"type": "uri", "value": "uri:1"},
                    "name": {"type": "literal", "value": "A"},
                    "spatial": {"type": "uri", "value": "place:1"},
                    "image": {"type": "uri", "value": "img:1"},
                },
                {
                    "s": {"type": "uri", "value": "uri:1"},
                    "name": {"type": "literal", "value": "A"},
                    "spatial": {"type": "uri", "value": "place:1"},
                    "image": {"type": "uri", "value": "img:2"},
                },
            ]
        },
    }
    rows = jps.parse_bindings(data, jps_type="史跡")
    assert rows[0]["spatial_uris"] == ["place:1"]
    assert rows[0]["image_urls"] == ["img:1", "img:2"]


def test_build_query_includes_type_limit_offset():
    q = jps.build_query(jps_type="史跡", limit=100, offset=200)
    assert "type:史跡" in q
    assert "LIMIT 100" in q
    assert "OFFSET 200" in q
    # required prefixes
    assert "PREFIX type:" in q
    assert "PREFIX schema:" in q


@responses.activate
def test_fetch_page_calls_endpoint_with_query_and_json_accept():
    responses.add(
        responses.GET,
        "https://jpsearch.go.jp/rdf/sparql/",
        json=SAMPLE_RESPONSE,
        status=200,
    )
    result = jps.fetch_page(jps_type="史跡", limit=100, offset=0)
    assert result == SAMPLE_RESPONSE

    assert len(responses.calls) == 1
    call = responses.calls[0]
    assert "application/sparql-results+json" in call.request.headers["Accept"]
    # query in URL
    assert "type%3A%E5%8F%B2%E8%B7%A1" in call.request.url or "type:史跡" in call.request.url


@responses.activate
def test_iter_rows_merges_a_subject_that_straddles_a_page_boundary():
    """A subject's bindings can span two pages — the values must not be lost."""
    page1 = {
        "head": {"vars": ["s", "name"]},
        "results": {
            "bindings": [
                {
                    "s": {"type": "uri", "value": "uri:A"},
                    "name": {"type": "literal", "value": "A"},
                },
                {
                    "s": {"type": "uri", "value": "uri:B"},
                    "name": {"type": "literal", "value": "B"},
                    "spatial": {"type": "uri", "value": "place:1"},
                },
            ]
        },
    }
    page2 = {
        "head": {"vars": ["s", "name", "spatial"]},
        "results": {
            "bindings": [
                # uri:B continues on page 2 with its second spatial value
                {
                    "s": {"type": "uri", "value": "uri:B"},
                    "name": {"type": "literal", "value": "B"},
                    "spatial": {"type": "uri", "value": "place:2"},
                },
                {
                    "s": {"type": "uri", "value": "uri:C"},
                    "name": {"type": "literal", "value": "C"},
                },
            ]
        },
    }
    page3 = {"head": {"vars": ["s", "name"]}, "results": {"bindings": []}}
    for p in (page1, page2, page3):
        responses.add(
            responses.GET, "https://jpsearch.go.jp/rdf/sparql/", json=p, status=200
        )

    rows = list(jps.iter_rows(jps_type="史跡", page_size=2))
    subjects = [r["subject_uri"] for r in rows]
    assert subjects == ["uri:A", "uri:B", "uri:C"]
    merged = next(r for r in rows if r["subject_uri"] == "uri:B")
    assert merged["spatial_uris"] == ["place:1", "place:2"]
    assert len(merged["raw"]) == 2


@responses.activate
def test_iter_rows_paginates_until_empty():
    page1 = {
        "head": {"vars": ["s", "name"]},
        "results": {
            "bindings": [
                {
                    "s": {"type": "uri", "value": f"uri:{i}"},
                    "name": {"type": "literal", "value": f"n{i}"},
                }
                for i in range(3)
            ]
        },
    }
    page2 = {"head": {"vars": ["s", "name"]}, "results": {"bindings": []}}
    responses.add(
        responses.GET, "https://jpsearch.go.jp/rdf/sparql/", json=page1, status=200
    )
    responses.add(
        responses.GET, "https://jpsearch.go.jp/rdf/sparql/", json=page2, status=200
    )

    rows = list(jps.iter_rows(jps_type="史跡", page_size=3))
    assert len(rows) == 3
    assert rows[0]["subject_uri"] == "uri:0"
    assert len(responses.calls) == 2
