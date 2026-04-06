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

## Analytical queries (src/queries.py)

| Query | What it answers |
|-------|----------------|
| `get_summary_stats` | Headline KPIs — total hours, artists, skip rate, top country |
| `get_top_artists` | Top N artists by hours listened (not play count) |
| `get_top_tracks` | Top N tracks by plays + completion rate |
| `get_hourly_heatmap` | Stream count for every hour × day of week combination |
| `get_monthly_trend` | Listening hours and skip rate per calendar month |
| `get_year_comparison` | Year-over-year streams, hours, skip rate, shuffle rate |
| `get_skip_analysis` | Skip rate broken down by year and country |
| `get_completion_leaders` | Tracks listened to fully, consistently (min 5 plays) |
| `get_hidden_gems` | Low play count but ≥90% completion, ≤10% skip rate |
| `get_listening_by_country` | Full behavioural profile split by DE vs PK |

**Design decisions:**
- Hours listened used instead of play count for artist ranking —
  a 3-minute skip inflates play count but contributes almost nothing
  to hours, making hours the more honest engagement metric
- Minimum play count filters (3–5) applied to completion and gem
  queries to ensure statistical reliability
- Country queries restricted to DE and PK — the two countries with
  meaningful sample sizes (14,070 and 9,740 streams respectively)

---

  ### Weather and listening behaviour

Historical weather data from Open-Meteo was joined to the listening
history to test whether external conditions affect Spotify usage.

**Germany (Berlin) — temperature drives listening more than rain:**

| Condition | Avg hours/day | Skip rate |
|-----------|--------------|-----------|
| Summer hot days (27°C+) | 3.92h | 62.1% |
| Summer warm days (19°C) | 2.57h | 52.5% |
| Winter cold days (0°C)  | 1.28h | 52.4% |
| Spring cool days (11°C) | 0.69h | 51.0% |

Counterintuitively, rainy days in Berlin did **not** produce more
listening — dry summer days actually had higher stream counts than
rainy ones. Heat appears to be a stronger driver than precipitation,
possibly reflecting heatwave days spent indoors.

**Pakistan (Karachi) — rain does drive listening:**

| Condition | Avg hours/day | Skip rate |
|-----------|--------------|-----------|
| Rainy Autumn days | 2.21h | 41.7% |
| Rainy Summer days (monsoon) | 1.21h | 35.6% |
| Dry Summer days | 0.77h | 35.7% |

In Karachi, rainy monsoon days correlate with noticeably more
listening — the opposite pattern to Berlin. This likely reflects
the difference between Berlin summer rain (brief, mild) and
Karachi monsoon rain (heavy, keeps you indoors for hours).

**Skip rate is consistently lower in Pakistan** (35–43%) than
Germany (49–62%) across all weather conditions — suggesting the
country effect is stronger than any weather effect on engagement.

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