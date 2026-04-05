# My Spotify Listening Dashboard

An end-to-end data analytics project built on one year of personal Spotify
streaming history — covering data engineering, SQL analytics, and an
interactive dashboard.

**Live demo:** 

---

## What this project covers

- Parsing and cleaning raw Spotify JSON export data
- Building a star-schema warehouse with DuckDB
- Enriching tracks with audio features via the Spotify API
- Analytical SQL queries covering engagement, time patterns, and taste evolution
- Interactive Streamlit dashboard with Plotly visualisations

---

## Project structure

---

## Dataset

| Metric | Value |
|--------|-------|
| Date range | Oct 2022 → Apr 2026 |
| Total play events | 23,826 |
| Total hours listened | 1,062 h |
| Unique artists | 1,171 |
| Unique tracks | 3,742 |
| Countries | DE (14,070) · PK (9,740) |
| Skip rate | 47.1% |

---

## Dataset

| Metric | Value |
|--------|-------|
| Date range | Oct 2022 → Apr 2026 |
| Raw play events | 52,192 |
| Clean play events | 23,826 |
| Total hours listened | 1,062 h |
| Unique artists | 1,171 |
| Unique tracks | 4,092 |
| Unique albums | 2,834 |
| Countries | DE · PK · US · TR |
| Overall skip rate | 47.1% |
| Top artist | Pritam (68.6 h) |

---

## Data pipeline
```
Streaming_History_Audio_*.json  (7 files, 2022–2026)
        ↓
  src/ingest.py
  • Merges all files, renames columns to snake_case
  • Drops podcasts, audiobooks, plays under 5 seconds
  • Derives time columns (hour, day, week, month, year, is_weekend)
  • Extracts country and platform from raw fields
  • Raw: 52,192 rows → Clean: 23,826 rows (28,366 junk removed)
  • Output: data/processed/streaming_clean.parquet
        ↓
  src/database.py
  • Builds star schema in DuckDB
  • dim_artists (1,171), dim_tracks (4,092), dim_date (23,826)
  • fact_streams (23,826 rows) — one row per play event
  • Output: data/processed/spotify.duckdb
        ↓
  src/enrich.py
  • Attempted Spotify API enrichment via sp.tracks()
  • Spotify has restricted API access for new apps since late 2024
  • Pivoted to deriving behavioural features from listening history:
      - completion_rate        : avg % of track duration actually played
      - skip_rate              : % of plays ended by skipping
      - shuffle_rate           : % of plays via shuffle mode
      - avg_plays_per_active_day: replay intensity on days track was played
  • Output: dim_track_metadata added to spotify.duckdb
        ↓
  src/queries.py              
  dashboard/app.py            
```

---

## Engineering decisions

**Spotify API deprecation**
The `audio_features` and `sp.tracks()` endpoints are restricted for
new developer apps as of late 2024. Rather than block on this, the
project derives equivalent behavioural features directly from the
raw listening history — completion rate, skip rate, and replay
intensity. These are arguably more meaningful than Spotify's generic
audio fingerprints because they reflect *your personal response* to
each track rather than its acoustic properties.

**Why DuckDB over SQLite or PostgreSQL**
DuckDB is a file-based analytical database optimised for columnar
queries — the same workload pattern as this project (aggregations
across 23,826 rows with multiple joins). Zero server setup, full SQL
support, and native parquet integration make it the right tool here.

**Star schema over a flat table**
Separating dimensions from facts keeps SQL clean, avoids data
repetition, and mirrors how real data warehouses are built. The
dim_date table in particular enables fast time-based slicing without
re-parsing timestamps on every query.

**28,366 rows removed in cleaning (54% of raw data)**
The extended Spotify export includes every app event — including
sub-5-second plays from accidental taps, app loads, and
autoplay-then-skip behaviour. Filtering these out gives a dataset
that reflects genuine listening intent rather than background noise.

---