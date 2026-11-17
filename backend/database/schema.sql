PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS datasets (
  dataset_id TEXT PRIMARY KEY,
  dataset_name TEXT NOT NULL,
  source_filename TEXT NOT NULL,
  transformed_filename TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_record_count INTEGER NOT NULL DEFAULT 0 CHECK (source_record_count >= 0),
  record_count INTEGER NOT NULL DEFAULT 0 CHECK (record_count >= 0),
  upload_date TEXT,
  loaded_at TEXT NOT NULL,
  processing_status TEXT NOT NULL CHECK (processing_status IN ('loaded', 'loaded_with_rejections'))
);

CREATE TABLE IF NOT EXISTS locations (
  location_id INTEGER PRIMARY KEY,
  place_name TEXT NOT NULL,
  country TEXT,
  UNIQUE (place_name, country)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_location_natural_key
  ON locations(lower(trim(place_name)), ifnull(country, ''));

CREATE TABLE IF NOT EXISTS water_metrics (
  metric_id INTEGER PRIMARY KEY,
  dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
  location_id INTEGER NOT NULL REFERENCES locations(location_id),
  source_record_id TEXT NOT NULL,
  publisher TEXT,
  metric_type TEXT,
  scope TEXT,
  measurement_period TEXT,
  measurement_month TEXT,
  reporting_year INTEGER,
  wue_l_per_kwh REAL,
  withdrawal_million_gal REAL,
  discharge_million_gal REAL,
  consumption_million_gal REAL,
  consumption_million_litres REAL,
  energy_wh_per_prompt REAL,
  water_ml_per_prompt REAL,
  water_million_litres REAL,
  water_scope TEXT,
  UNIQUE (dataset_id, source_record_id)
);

CREATE TABLE IF NOT EXISTS load_history (
  load_id INTEGER PRIMARY KEY,
  dataset_id TEXT NOT NULL,
  source_filename TEXT NOT NULL,
  transformed_filename TEXT NOT NULL,
  records_read INTEGER NOT NULL DEFAULT 0,
  records_inserted INTEGER NOT NULL DEFAULT 0,
  records_rejected INTEGER NOT NULL DEFAULT 0,
  duplicate_records INTEGER NOT NULL DEFAULT 0,
  loaded_at TEXT NOT NULL,
  load_status TEXT NOT NULL,
  message TEXT
);

CREATE TABLE IF NOT EXISTS data_quality_logs (
  log_id INTEGER PRIMARY KEY,
  dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
  quality_metric TEXT NOT NULL,
  issue_count INTEGER NOT NULL CHECK (issue_count >= 0),
  report_date TEXT NOT NULL,
  details TEXT
);

CREATE INDEX IF NOT EXISTS idx_water_dataset ON water_metrics(dataset_id);
CREATE INDEX IF NOT EXISTS idx_water_location ON water_metrics(location_id);
CREATE INDEX IF NOT EXISTS idx_water_period ON water_metrics(measurement_period);
CREATE INDEX IF NOT EXISTS idx_location_country ON locations(country);
CREATE INDEX IF NOT EXISTS idx_load_history_dataset ON load_history(dataset_id, loaded_at);
