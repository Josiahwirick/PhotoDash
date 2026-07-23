PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS people (
  id         INTEGER PRIMARY KEY,
  name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
  color      TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS photos (
  id               INTEGER PRIMARY KEY,
  filename         TEXT NOT NULL UNIQUE,
  original_name    TEXT NOT NULL,
  width            INTEGER NOT NULL,
  height           INTEGER NOT NULL,
  rotated          INTEGER NOT NULL DEFAULT 0,
  rotation_degrees INTEGER NOT NULL DEFAULT 0,
  mime_type        TEXT NOT NULL,
  uploaded_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  active           INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS calendar_entries (
  id         INTEGER PRIMARY KEY,
  entry_date TEXT NOT NULL,
  person_id  INTEGER REFERENCES people(id) ON DELETE SET NULL,
  entry_type TEXT NOT NULL CHECK (entry_type IN ('chore','appointment','reminder')),
  text       TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_calendar_entries_date ON calendar_entries(entry_date);

CREATE TABLE IF NOT EXISTS weather_cache (
  forecast_date   TEXT PRIMARY KEY,
  low_c           REAL,
  high_c          REAL,
  current_c       REAL,
  condition       TEXT NOT NULL,
  condition_label TEXT NOT NULL,
  fetched_at      TEXT NOT NULL,
  source          TEXT NOT NULL DEFAULT 'open-meteo'
);

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
