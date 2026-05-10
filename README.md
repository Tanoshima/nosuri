# nosuri

A personal search & map service for long-lasting places — historic sites, geosites, and similar locations. Eventually intended for public release.

## Tech Stack

| Layer | Technology |
|---|---|
| Database | PostgreSQL 16 + PostGIS |
| Backend | Go (REST API, image processing, OD batch jobs) |
| Frontend | React SPA (`react-leaflet`, PWA) |
| Data ingestion | Python (open-data fetchers) |
| Local dev | Devcontainer + Nix flake (`nix-direnv`) |
| Production (planned) | AWS — RDS (PostGIS), ECS / App Runner, S3 |

## Local Development Environment

The development environment is fully reproducible via a devcontainer powered by Nix. Open the project in VS Code and choose **Reopen in Container** — that's it.

### What runs inside the container

- **Image**: `ghcr.io/cachix/devenv/devcontainer:latest` (used as a Nix base; devenv itself is no longer used)
- **PostgreSQL 16 + PostGIS**: started in the background on container start via `pg-up`, listening on `127.0.0.1:5432`
- **Python 3.14** managed by [uv](https://docs.astral.sh/uv/) (deps in `pyproject.toml`, locked in `uv.lock`); `uv sync` runs automatically on shell entry; venv at `.venv/`
- **Claude Code** (`claude` CLI) — host's `~/.claude` is bind-mounted into the container so login state is preserved
- **direnv + nix-direnv** auto-activation of the flake dev shell

### File layout

```
.devcontainer/devcontainer.json   # Devcontainer definition
.devcontainer/postCreate.sh       # Installs nix-direnv, wires direnv hook
flake.nix                         # Dev shell + pg-up / pg-down scripts
.envrc                            # `use flake` + PATH_add bin
db/init.sql                       # PostGIS extension setup
pyproject.toml                    # Python project + dependencies (managed by uv)
uv.lock                           # uv lockfile (committed for reproducibility)
scripts/                          # Open-data ingestion scripts (Python)
```

### Connecting to the database

The following environment variables are exported automatically inside the dev shell:

| Variable | Value |
|---|---|
| `DATABASE_URL` | `postgresql://127.0.0.1:5432/nosuri` |
| `PGHOST` | `127.0.0.1` |
| `PGPORT` | `5432` |
| `PGDATABASE` | `nosuri` |
| `PGUSER` | `postgres` |
| `PGDATA` | `$PWD/.local/state/postgres` |

### Useful commands (inside the container)

```bash
pg-up                    # Start PostgreSQL (auto-run on container start)
pg-down                  # Stop PostgreSQL
psql $DATABASE_URL       # Connect to the database
uv add <package>         # Add a Python dependency (updates pyproject.toml + uv.lock)
uv run python <file>.py  # Run a Python script in the project venv
```

## Data Strategy

To allow open data to be re-ingested without overwriting hand-curated content, the schema separates concerns:

- **Raw tables** — direct mirror of upstream open data (re-ingested freely).
- **Main tables** — application-facing data, may include manual edits and links to raw rows.

Classification uses three orthogonal axes — hierarchical **categories**, flat **tags**, and **era / period** metadata — to support cross-cutting search.

## Open Data Sources

Initial focus is on historic sites (well-structured data), expanding to geosites later.

- **Japan Search API** — unified national cultural-property database
- **MLIT National Land Numerical Information** — GeoJSON bulk download, ideal for seeding
- **G-Spatial Information Center** — local government / geopark datasets
- **AIST Seamless Geological Map API** — base layer for geosite views
- **OpenStreetMap (Overpass API) / Wikidata** — broad fallback coverage
