# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

Personal search & map service for long-lasting places (historic sites, geosites in Japan), with eventual public release. See `README.md` for the tech stack and `temp.md` for the original product brief (Japanese).

The project is in an early **"scrap & build"** phase — application code does not yet exist. Current scope is data infrastructure (PostgreSQL + PostGIS) and Python scripts to ingest open data. Prefer minimal, working solutions over premature abstraction; structures (Python packages, Go modules, etc.) should appear only when there is enough code to justify them.

User communication and the product brief are in Japanese. Code, identifiers, and comments are in English.

## Development environment

The devcontainer provides a Nix flake-based dev shell, auto-activated by direnv (via `nix-direnv`) on `cd` into the project root. PostgreSQL is **not** auto-started — run `pg-up` to start it (and `pg-down` to stop). On container start, `pg-up` is run automatically in the background.

`DATABASE_URL` and `PG{HOST,PORT,DATABASE,USER}` are exported by the flake's `shellHook` automatically — no `.env` file is needed for local DB access. `PGDATA` points to `.local/state/postgres` inside the project.

Common commands (inside the dev shell):
- `pg-up` — initialize (first time) and start PostgreSQL, create the `nosuri` DB and apply `db/init.sql` (applied on every start)
- `pg-down` — stop PostgreSQL
- `psql $DATABASE_URL` — connect to the database
- `cd ingest && uv run python scripts/<file>.py` — run an ingestion script in the project venv

All Python code (package, scripts, tests, `pyproject.toml`, `uv.lock`) lives under `ingest/`. The root is reserved for cross-language concerns (`db/`, `flake.nix`, docs, devcontainer); future Go/React code will sit alongside `ingest/` (e.g. `api/`, `web/`).

Python dependencies are managed by [uv](https://docs.astral.sh/uv/). `uv sync` runs automatically on shell entry against `ingest/pyproject.toml`; the venv lives at `ingest/.venv/`. To add a dependency: `cd ingest && uv add <package>` (updates `ingest/pyproject.toml` and `ingest/uv.lock`). Do not edit the venv directly with `pip`.

To change the dev shell (packages, env vars, postgres extensions): edit `flake.nix`. PostgreSQL extensions are configured via `pkgs.postgresql_16.withPackages`.

`db/init.sql` is the authoritative schema entry point: it enables the PostGIS extensions and `\ir`-includes the per-table DDL files (`db/raw_jps_shiseki.sql`, `db/raw_jps_item_api.sql`). Every statement is `CREATE ... IF NOT EXISTS`, so it is idempotent and `pg-up` applies it on **every** start; it can also be run by hand (`psql $DATABASE_URL -f db/init.sql`).

Because of `IF NOT EXISTS`, editing a table file does **not** change a table that already exists. Reshaping one (column type, primary key, index) needs a numbered file in `db/migrations/`, applied manually (`psql $DATABASE_URL -f db/migrations/000N_*.sql`); alternatively reset the cluster (`pg-down && rm -rf .local/state/postgres && pg-up`).

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
