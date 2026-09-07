-- Authoritative schema entry point. Idempotent — safe to re-run at any time:
--     psql $DATABASE_URL -f db/init.sql
-- `pg-up` runs it on every start. Reshaping an existing table (changing a
-- column type, a primary key, an index) is NOT covered by these CREATE ...
-- IF NOT EXISTS statements — add a file under db/migrations/ for that.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

\ir raw_jps_shiseki.sql
\ir raw_jps_item_api.sql
