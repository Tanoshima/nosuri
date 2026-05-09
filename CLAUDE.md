# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

Personal search & map service for long-lasting places (historic sites, geosites in Japan), with eventual public release. See `README.md` for the tech stack and `temp.md` for the original product brief (Japanese).

The project is in an early **"scrap & build"** phase — application code does not yet exist. Current scope is data infrastructure (PostgreSQL + PostGIS) and Python scripts to ingest open data. Prefer minimal, working solutions over premature abstraction; structures (Python packages, Go modules, etc.) should appear only when there is enough code to justify them.

User communication and the product brief are in Japanese. Code, identifiers, and comments are in English.

## Development environment

The devcontainer auto-starts PostgreSQL 16 + PostGIS via `devenv up` on container start. The devenv shell is auto-activated by direnv on `cd` into the project root, so commands below are typically run as-is in any terminal inside the container.

`DATABASE_URL` and `PG{HOST,PORT,DATABASE,USER}` are exported by devenv automatically — no `.env` file is needed for local DB access.

Common commands:
- `devenv up` — start PostgreSQL (already auto-run on container start)
- `psql $DATABASE_URL` — connect to the database
- `uv run python scripts/<file>.py` — run an ingestion script in the project venv

Python dependencies are managed by [uv](https://docs.astral.sh/uv/). `uv sync` runs automatically on shell entry; the venv lives at `.devenv/state/venv`. To add a dependency: `uv add <package>` (updates `pyproject.toml` and `uv.lock`). Do not edit the venv directly with `pip`.
To change PostgreSQL configuration or extensions: edit `devenv.nix` under `services.postgres`.
SQL run on first cluster initialization lives in `db/init.sql` (currently enables `postgis` and `postgis_topology`). It does **not** re-run on existing clusters — to apply changes after the DB exists, drop the cluster (`rm -rf .devenv/state/postgres`) or run the SQL manually.

## Architecture notes

### Raw vs. main tables

Open data is re-ingested periodically without overwriting hand-curated content. The schema separates two layers:
- **Raw tables** — 1:1 mirror of upstream open data; freely re-ingested or rebuilt. Ingestion scripts write here only.
- **Main tables** — application-facing; may include manual edits, links back to raw rows, and merged data from multiple sources.

Code that ingests open data must not write directly to main tables. Promotion from raw → main is a separate concern (not yet implemented).

### Spatial data

Latitude/longitude is stored as PostGIS `geometry`. Express distance and range queries in SQL (`ST_DWithin`, `ST_Distance`, etc.) rather than computing in application code.

### Classification

Three orthogonal axes are combined for cross-cutting search: hierarchical **categories** (e.g. 城跡 → 山城), flat **tags**, and **era / period**. New entity types should fit into all three rather than introducing a fourth axis.
