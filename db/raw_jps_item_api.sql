CREATE TABLE IF NOT EXISTS raw_jps_item_api (
    subject_uri          text PRIMARY KEY REFERENCES raw_jps_shiseki(subject_uri) ON DELETE CASCADE,
    geom                 geometry(Point, 4326),
    link_url             text,
    description          text,
    contents_rights_type text,
    raw                  jsonb NOT NULL,
    fetched_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS raw_jps_item_api_geom_gix      ON raw_jps_item_api USING GIST (geom);
CREATE INDEX IF NOT EXISTS raw_jps_item_api_rights_idx    ON raw_jps_item_api (contents_rights_type);
