-- Mirror of the JPS SPARQL result set, one row per (subject, type).
--
-- A subject can be published under several JPS types (e.g. both 史跡 and 名勝),
-- and every OPTIONAL predicate can be multi-valued, so the primary key is the
-- (subject, type) pair and the multi-valued predicates are arrays. `raw` keeps
-- every binding that produced the row so new columns can be derived later
-- without re-querying the endpoint.
CREATE TABLE IF NOT EXISTS raw_jps_shiseki (
    subject_uri  text NOT NULL,
    jps_type     text NOT NULL,
    name         text NOT NULL,
    spatial_uris text[] NOT NULL DEFAULT '{}',
    geohash_uris text[] NOT NULL DEFAULT '{}',
    temporals    text[] NOT NULL DEFAULT '{}',
    image_urls   text[] NOT NULL DEFAULT '{}',
    source_infos text[] NOT NULL DEFAULT '{}',
    raw          jsonb NOT NULL,
    fetched_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (subject_uri, jps_type)
);

CREATE INDEX IF NOT EXISTS raw_jps_shiseki_jps_type_idx ON raw_jps_shiseki (jps_type);
CREATE INDEX IF NOT EXISTS raw_jps_shiseki_spatial_gix  ON raw_jps_shiseki USING GIN (spatial_uris);
