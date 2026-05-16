"""JPS (Japan Search) SPARQL fetcher and parser.

Fetches records of a given `type:` (e.g. 史跡) from the public SPARQL endpoint
and converts each result binding into a dict suitable for upserting into
the `raw_jps_shiseki` table.
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


def parse_bindings(response: dict[str, Any], *, jps_type: str) -> list[dict[str, Any]]:
    bindings = response.get("results", {}).get("bindings", [])
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for b in bindings:
        subject = _v(b, "s")
        if subject is None or subject in seen:
            continue
        seen.add(subject)
        rows.append(
            {
                "subject_uri": subject,
                "jps_type": jps_type,
                "name": _v(b, "name") or "",
                "spatial_uri": _v(b, "spatial"),
                "geohash_uri": _v(b, "geo"),
                "temporal": _v(b, "temporal"),
                "image_url": _v(b, "image"),
                "source_info": _v(b, "source"),
                "raw": b,
            }
        )
    return rows


def iter_rows(
    *,
    jps_type: str,
    page_size: int = DEFAULT_PAGE_SIZE,
    endpoint: str = SPARQL_ENDPOINT,
    sleep_between: float = 0.0,
) -> Iterator[dict[str, Any]]:
    # Multi-valued OPTIONAL bindings (e.g. multiple spatial values) can make
    # the same ?s span page boundaries, so dedupe across the whole run too.
    yielded: set[str] = set()
    offset = 0
    while True:
        response = fetch_page(
            jps_type=jps_type, limit=page_size, offset=offset, endpoint=endpoint
        )
        bindings = response.get("results", {}).get("bindings", [])
        if not bindings:
            return
        for row in parse_bindings(response, jps_type=jps_type):
            if row["subject_uri"] in yielded:
                continue
            yielded.add(row["subject_uri"])
            yield row
        if len(bindings) < page_size:
            return
        offset += page_size
        if sleep_between > 0:
            time.sleep(sleep_between)
