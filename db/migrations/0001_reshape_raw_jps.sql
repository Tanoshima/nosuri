-- 0001: make the raw JPS tables lossless and safe to rebuild independently.
--
--   * raw_jps_item_api no longer references raw_jps_shiseki (ON DELETE CASCADE
--     meant rebuilding the cheap table wiped the rate-limited one).
--   * raw_jps_shiseki is keyed by (subject_uri, jps_type) so a subject
--     published under several types keeps a row per type.
--   * multi-valued SPARQL predicates become arrays, and `raw` becomes a JSON
--     array of every binding behind the row.
--   * link_url is dropped — it was never written (the value lives in
--     raw_jps_item_api.link_url).
--
-- Existing rows are converted in place; values dropped by the old
-- first-binding-wins ingest are not recoverable, so re-run
-- scripts/ingest_jps_shiseki.py afterwards to backfill them.
BEGIN;

ALTER TABLE raw_jps_item_api
    DROP CONSTRAINT IF EXISTS raw_jps_item_api_subject_uri_fkey;
DROP INDEX IF EXISTS raw_jps_item_api_rights_idx;

ALTER TABLE raw_jps_shiseki DROP COLUMN IF EXISTS link_url;

ALTER TABLE raw_jps_shiseki
    ALTER COLUMN spatial_uri TYPE text[]
        USING CASE WHEN spatial_uri IS NULL THEN '{}' ELSE ARRAY[spatial_uri] END,
    ALTER COLUMN spatial_uri SET DEFAULT '{}',
    ALTER COLUMN spatial_uri SET NOT NULL,
    ALTER COLUMN geohash_uri TYPE text[]
        USING CASE WHEN geohash_uri IS NULL THEN '{}' ELSE ARRAY[geohash_uri] END,
    ALTER COLUMN geohash_uri SET DEFAULT '{}',
    ALTER COLUMN geohash_uri SET NOT NULL,
    ALTER COLUMN temporal TYPE text[]
        USING CASE WHEN temporal IS NULL THEN '{}' ELSE ARRAY[temporal] END,
    ALTER COLUMN temporal SET DEFAULT '{}',
    ALTER COLUMN temporal SET NOT NULL,
    ALTER COLUMN image_url TYPE text[]
        USING CASE WHEN image_url IS NULL THEN '{}' ELSE ARRAY[image_url] END,
    ALTER COLUMN image_url SET DEFAULT '{}',
    ALTER COLUMN image_url SET NOT NULL,
    ALTER COLUMN source_info TYPE text[]
        USING CASE WHEN source_info IS NULL THEN '{}'
                   ELSE ARRAY[source_info #>> '{}'] END,
    ALTER COLUMN source_info SET DEFAULT '{}',
    ALTER COLUMN source_info SET NOT NULL;

ALTER TABLE raw_jps_shiseki RENAME COLUMN spatial_uri TO spatial_uris;
ALTER TABLE raw_jps_shiseki RENAME COLUMN geohash_uri TO geohash_uris;
ALTER TABLE raw_jps_shiseki RENAME COLUMN temporal    TO temporals;
ALTER TABLE raw_jps_shiseki RENAME COLUMN image_url   TO image_urls;
ALTER TABLE raw_jps_shiseki RENAME COLUMN source_info TO source_infos;

UPDATE raw_jps_shiseki SET raw = jsonb_build_array(raw)
 WHERE jsonb_typeof(raw) <> 'array';

ALTER TABLE raw_jps_shiseki DROP CONSTRAINT IF EXISTS raw_jps_shiseki_pkey;
ALTER TABLE raw_jps_shiseki ADD PRIMARY KEY (subject_uri, jps_type);

DROP INDEX IF EXISTS raw_jps_shiseki_spatial_idx;
CREATE INDEX IF NOT EXISTS raw_jps_shiseki_spatial_gix
    ON raw_jps_shiseki USING GIN (spatial_uris);

COMMIT;
