{
  description = "nosuri devshell";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = f:
        nixpkgs.lib.genAttrs systems (system:
          f (import nixpkgs {
            inherit system;
            config.allowUnfree = true;
          }));
    in
    {
      devShells = forAllSystems (pkgs:
        let
          postgres = pkgs.postgresql_16.withPackages (p: [ p.postgis ]);

          pg-up = pkgs.writeShellScriptBin "pg-up" ''
            set -euo pipefail
            : "''${PGDATA:?PGDATA not set — open the dev shell first}"
            mkdir -p "$(dirname "$PGDATA")"
            if [ ! -f "$PGDATA/PG_VERSION" ]; then
              rm -rf "$PGDATA"
              initdb -D "$PGDATA" \
                --auth-local=trust --auth-host=trust \
                --username="$PGUSER" --no-locale --encoding=UTF8 >/dev/null
              {
                echo "listen_addresses = '127.0.0.1'"
                echo "unix_socket_directories = '$PGDATA'"
              } >> "$PGDATA/postgresql.conf"
            fi
            if pg_ctl -D "$PGDATA" status >/dev/null 2>&1; then
              echo "postgres already running"
            else
              pg_ctl -D "$PGDATA" -l "$PGDATA/postgres.log" \
                -o "-p $PGPORT -k $PGDATA" start
            fi
            if ! psql -h "$PGHOST" -U "$PGUSER" -d postgres -tAc \
                "SELECT 1 FROM pg_database WHERE datname='$PGDATABASE'" \
                | grep -q 1; then
              createdb -h "$PGHOST" -U "$PGUSER" "$PGDATABASE"
            fi
            # Idempotent, so apply it on every start — not just on DB creation.
            if [ -f db/init.sql ]; then
              psql -h "$PGHOST" -U "$PGUSER" -d "$PGDATABASE" \
                -v ON_ERROR_STOP=1 -q -f db/init.sql
            fi
          '';

          pg-down = pkgs.writeShellScriptBin "pg-down" ''
            set -e
            : "''${PGDATA:?PGDATA not set — open the dev shell first}"
            pg_ctl -D "$PGDATA" stop || true
          '';
        in
        {
          default = pkgs.mkShell {
            packages = [
              pkgs.git
              pkgs.curl
              pkgs.claude-code
              pkgs.uv
              postgres
              pg-up
              pg-down
            ];

            shellHook = ''
              export DATABASE_URL="postgresql://127.0.0.1:5432/nosuri"
              export PGHOST="127.0.0.1"
              export PGPORT="5432"
              export PGDATABASE="nosuri"
              export PGUSER="postgres"
              export PGDATA="$PWD/.local/state/postgres"

              if [ -f ingest/pyproject.toml ] && command -v uv >/dev/null; then
                (cd ingest && uv sync --quiet) 2>/dev/null || true
              fi
            '';
          };
        });
    };
}
