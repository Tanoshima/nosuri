{ pkgs, ... }:
{
  packages = [
    pkgs.git
    pkgs.curl
    pkgs.claude-code
  ];

  languages.python = {
    enable = true;
    version = "3.14";
    venv.enable = true;
    uv = {
      enable = true;
      sync.enable = true;
    };
  };

  services.postgres = {
    enable = true;
    package = pkgs.postgresql_16;
    extensions = extensions: [ extensions.postgis ];
    port = 5432;
    listen_addresses = "127.0.0.1";
    initialDatabases = [
      {
        name = "nosuri";
        schema = ./db/init.sql;
      }
    ];
  };

  env = {
    DATABASE_URL = "postgresql://127.0.0.1:5432/nosuri";
    PGHOST = "127.0.0.1";
    PGPORT = "5432";
    PGDATABASE = "nosuri";
    PGUSER = "postgres";
  };
}
