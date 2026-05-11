"""Tests for the JPS simple Web API per-item fetcher/parser."""
from __future__ import annotations

import pytest
import responses

from nosuri import jps_item


SAMPLE_RESPONSE = {
    "id": "SHUGYOKU1-2341034",
    "common": {
        "id": "SHUGYOKU1-2341034",
        "title": "御前原城跡",
        "linkUrl": "https://www.digitalmuseum.pref.tochigi.lg.jp/museweb/detail?cls=collect3a&pkey=2341034",
        "description": "本丸東西185m、南北180m...",
        "contentsRightsType": "cc-by",
        "provider": "TDMSHUGYOKU",
    },
    "coordinates": {"lat": 36.78824234008789, "lon": 139.9445343017578},
}


def test_parse_item_extracts_geom_link_description_rights():
    row = jps_item.parse_item(SAMPLE_RESPONSE, subject_uri="https://jpsearch.go.jp/data/SHUGYOKU1-2341034")
    assert row["subject_uri"] == "https://jpsearch.go.jp/data/SHUGYOKU1-2341034"
    assert row["lat"] == pytest.approx(36.78824, abs=1e-4)
    assert row["lon"] == pytest.approx(139.94453, abs=1e-4)
    assert row["link_url"].startswith("https://www.digitalmuseum.pref.tochigi.lg.jp/")
    assert row["description"].startswith("本丸東西")
    assert row["contents_rights_type"] == "cc-by"
    assert row["raw"] == SAMPLE_RESPONSE


def test_parse_item_handles_missing_coordinates():
    response = {"id": "x", "common": {"id": "x", "title": "t", "linkUrl": "u"}}
    row = jps_item.parse_item(response, subject_uri="uri:x")
    assert row["lat"] is None
    assert row["lon"] is None
    assert row["link_url"] == "u"
    assert row["description"] is None
    assert row["contents_rights_type"] is None


def test_parse_item_handles_missing_common():
    response = {"id": "x"}
    row = jps_item.parse_item(response, subject_uri="uri:x")
    assert row["link_url"] is None
    assert row["lat"] is None


def test_subject_uri_to_item_id_strips_prefix():
    assert jps_item.subject_uri_to_item_id(
        "https://jpsearch.go.jp/data/SHUGYOKU1-2341034"
    ) == "SHUGYOKU1-2341034"
    assert jps_item.subject_uri_to_item_id(
        "https://jpsearch.go.jp/data/adeac-R100000094_I000140690_00"
    ) == "adeac-R100000094_I000140690_00"


@responses.activate
def test_fetch_item_calls_api_and_returns_json():
    responses.add(
        responses.GET,
        "https://jpsearch.go.jp/api/item/SHUGYOKU1-2341034",
        json=SAMPLE_RESPONSE,
        status=200,
    )
    result = jps_item.fetch_item("SHUGYOKU1-2341034")
    assert result == SAMPLE_RESPONSE
    assert len(responses.calls) == 1


@responses.activate
def test_fetch_item_url_encodes_id_with_slashes():
    """item IDs can contain characters that need URL encoding."""
    item_id = "adeac-R100000094_I000140690_00"
    responses.add(
        responses.GET,
        f"https://jpsearch.go.jp/api/item/{item_id}",
        json={"id": item_id},
        status=200,
    )
    jps_item.fetch_item(item_id)
    assert len(responses.calls) == 1


@responses.activate
def test_fetch_item_returns_none_on_404():
    responses.add(
        responses.GET,
        "https://jpsearch.go.jp/api/item/missing",
        json={"error": "not found"},
        status=404,
    )
    assert jps_item.fetch_item("missing") is None
