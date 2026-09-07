"""JPS (Japan Search) SPARQL fetcher and parser.

Fetches records of a given `type:` (e.g. 史跡) from the public SPARQL endpoint
and groups the result bindings into one dict per subject, suitable for
upserting into the `raw_jps_shiseki` table.
"""
from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import requests


SPARQL_ENDPOINT = "https://jpsearch.go.jp/rdf/sparql/"
DEFAULT_PAGE_SIZE = 500
DEFAULT_USER_AGENT = "nosuri-jps-ingest/0.0 (+https://github.com/)"


def build_query(*, jps_type: str, limit: int, offset: int) -> str:
    return f"""\
PREFIX type: <https://jpsearch.go.jp/term/type/>
PREFIX schema: <http://schema.org/>
PREFIX jps: <https://jpsearch.go.jp/term/property/>
SELECT ?s ?name ?spatial ?geo ?temporal ?image ?source WHERE {{
  ?s a type:{jps_type} ;
     schema:name ?name .
  OPTIONAL {{ ?s schema:spatial ?spatial .
             OPTIONAL {{ ?spatial schema:geo ?geo }} }}
  OPTIONAL {{ ?s schema:temporal ?temporal }}
  OPTIONAL {{ ?s schema:image ?image }}
  OPTIONAL {{ ?s jps:sourceInfo ?source }}
}}
ORDER BY ?s
LIMIT {limit} OFFSET {offset}
"""


def fetch_page(
    *,
    jps_type: str,
    limit: int,
    offset: int,
    endpoint: str = SPARQL_ENDPOINT,
    timeout: float = 60.0,
) -> dict[str, Any]:
    query = build_query(jps_type=jps_type, limit=limit, offset=offset)
    resp = requests.get(
        endpoint,
        params={"query": query},
        headers={
            "Accept": "application/sparql-results+json",
            "User-Agent": DEFAULT_USER_AGENT,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def _v(binding: dict[str, Any], key: str) -> str | None:
    cell = binding.get(key)
    if cell is None:
        return None
    return cell.get("value")


_ARRAY_FIELDS = (
    ("spatial_uris", "spatial"),
    ("geohash_uris", "geo"),
    ("temporals", "temporal"),
    ("image_urls", "image"),
    ("source_infos", "source"),
)


def _append_binding(row: dict[str, Any], binding: dict[str, Any]) -> None:
    """Fold one SPARQL binding into an existing row for the same subject."""
    if not row["name"]:
        row["name"] = _v(binding, "name") or ""
    for field, key in _ARRAY_FIELDS:
        value = _v(binding, key)
        if value is not None and value not in row[field]:
            row[field].append(value)
    row["raw"].append(binding)


def _new_row(subject_uri: str, *, jps_type: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "subject_uri": subject_uri,
        "jps_type": jps_type,
        "name": "",
        "raw": [],
    }
    for field, _ in _ARRAY_FIELDS:
        row[field] = []
    return row


def parse_bindings(response: dict[str, Any], *, jps_type: str) -> list[dict[str, Any]]:
    """Group bindings into one row per subject, in the order subjects appear.

    Multi-valued OPTIONALs (several spatial values, several images, ...) arrive
    as repeated bindings for the same ?s; every value is kept.
    """
    bindings = response.get("results", {}).get("bindings", [])
    rows: dict[str, dict[str, Any]] = {}
    for b in bindings:
        subject = _v(b, "s")
        if subject is None:
            continue
        row = rows.get(subject)
        if row is None:
            row = rows[subject] = _new_row(subject, jps_type=jps_type)
        _append_binding(row, b)
    return list(rows.values())


def copy_row(row: dict[str, Any]) -> dict[str, Any]:
    """Copy a row deeply enough that merging into it leaves the source alone."""
    copied = dict(row)
    copied["raw"] = list(row["raw"])
    for field, _ in _ARRAY_FIELDS:
        copied[field] = list(row.get(field) or [])
    return copied


def merge_rows(into: dict[str, Any], other: dict[str, Any]) -> dict[str, Any]:
    """Merge `other` into `into` (same subject); returns `into`."""
    if not into["name"]:
        into["name"] = other["name"]
    for field, _ in _ARRAY_FIELDS:
        for value in other[field]:
            if value not in into[field]:
                into[field].append(value)
    into["raw"].extend(other["raw"])
    return into


def iter_rows(
    *,
    jps_type: str,
    page_size: int = DEFAULT_PAGE_SIZE,
    endpoint: str = SPARQL_ENDPOINT,
    sleep_between: float = 0.0,
) -> Iterator[dict[str, Any]]:
    # ORDER BY ?s keeps a subject's bindings adjacent, but a subject with
    # several bindings can still straddle a page boundary — hold the last row
    # of each page back and merge it with the next page's first row.
    pending: dict[str, Any] | None = None
    offset = 0
    while True:
        response = fetch_page(
            jps_type=jps_type, limit=page_size, offset=offset, endpoint=endpoint
        )
        bindings = response.get("results", {}).get("bindings", [])
        if not bindings:
            break
        for row in parse_bindings(response, jps_type=jps_type):
            if pending is None:
                pending = row
            elif pending["subject_uri"] == row["subject_uri"]:
                merge_rows(pending, row)
            else:
                yield pending
                pending = row
        if len(bindings) < page_size:
            break
        offset += page_size
        if sleep_between > 0:
            time.sleep(sleep_between)
    if pending is not None:
        yield pending
