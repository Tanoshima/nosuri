-- Mirror of the JPS simple Web API (`/api/item/{id}`), one row per subject.
--
-- Deliberately NOT a foreign key onto raw_jps_shiseki: this table is the
-- expensive one to rebuild (one rate-limited HTTP call per row), while
-- raw_jps_shiseki is a few minutes of SPARQL and is rebuilt freely. A FK would
-- make rebuilding the cheap table destroy the expensive one. Rows whose
-- subject has disappeared upstream are dropped by the join instead.
CREATE TABLE IF NOT EXISTS raw_jps_item_api (
    subject_uri          text PRIMARY KEY,
    geom                 geometry(Point, 4326),
    link_url             text,
    description          text,
    contents_rights_type text,
    raw                  jsonb NOT NULL,
    fetched_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS raw_jps_item_api_geom_gix ON raw_jps_item_api USING GIST (geom);
