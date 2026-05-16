"""JPS simple Web API per-item fetcher.

Calls `GET https://jpsearch.go.jp/api/item/{id}` to enrich each JPS subject with
precise coordinates, source linkUrl, description, and rights metadata.
"""
from __future__ import annotations

import urllib.parse
from typing import Any

import requests


ITEM_ENDPOINT = "https://jpsearch.go.jp/api/item/"
SUBJECT_URI_PREFIX = "https://jpsearch.go.jp/data/"
DEFAULT_USER_AGENT = "nosuri-jps-ingest/0.0 (+https://github.com/)"


def subject_uri_to_item_id(subject_uri: str) -> str:
    if subject_uri.startswith(SUBJECT_URI_PREFIX):
        return subject_uri[len(SUBJECT_URI_PREFIX):]
    return subject_uri


def fetch_item(item_id: str, *, timeout: float = 30.0) -> dict[str, Any] | None:
    url = ITEM_ENDPOINT + urllib.parse.quote(item_id, safe="")
    resp = requests.get(
        url,
        headers={"Accept": "application/json", "User-Agent": DEFAULT_USER_AGENT},
        timeout=timeout,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def parse_item(response: dict[str, Any], *, subject_uri: str) -> dict[str, Any]:
    common = response.get("common") or {}
    coords = response.get("coordinates") or common.get("coordinates") or {}
    return {
        "subject_uri": subject_uri,
        "lat": coords.get("lat"),
        "lon": coords.get("lon"),
        "link_url": common.get("linkUrl"),
        "description": common.get("description"),
        "contents_rights_type": common.get("contentsRightsType"),
        "raw": response,
    }
