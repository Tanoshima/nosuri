CREATE TABLE IF NOT EXISTS raw_jps_shiseki (
    subject_uri text PRIMARY KEY,
    jps_type    text NOT NULL,
    name        text NOT NULL,
    spatial_uri text,
    geohash_uri text,
    temporal    text,
    image_url   text,
    link_url    text,
    source_info jsonb,
    raw         jsonb NOT NULL,
    fetched_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS raw_jps_shiseki_jps_type_idx  ON raw_jps_shiseki (jps_type);
CREATE INDEX IF NOT EXISTS raw_jps_shiseki_spatial_idx   ON raw_jps_shiseki (spatial_uri);
