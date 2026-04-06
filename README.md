# Spotify Listening Intelligence

An end-to-end data analytics project built on 4 years of personal Spotify
streaming history — covering data engineering, SQL analytics, weather
correlation, and an interactive dashboard.

**Live demo:** https://my-spotify-analysis.streamlit.app/

---

## Overview

Most Spotify portfolio projects stop at "here are my top artists."
This one goes further; building a proper data warehouse, enriching
the data with historical weather, and asking questions like:

- Did moving from Pakistan to Germany change how you listen to music?
- Do you listen more on rainy days — and does the answer differ by country?
- Which tracks do you always hear in full, and which do you skip every time?
- How has your listening intensity changed year over year?

The dataset spans **Oct 2022 → Apr 2026** across two countries,
covering life in both Karachi (PK) and Berlin (DE).

---

## Live demo

**https://my-spotify-analysis.streamlit.app/**

Five pages:

| Page | What it shows |
|------|--------------|
| Overview | KPI cards, top artists by hours, year-over-year volume |
| Time patterns | Hour × day heatmap, monthly trend, skip rate over time |
| Engagement | Skip analysis, completion leaders, hidden gems, scatter |
| DE vs PK | Full behavioural comparison between Germany and Pakistan |
| Weather | Listening intensity vs season, rainy vs dry days, temperature |

---

## Dataset

| Metric | Value |
|--------|-------|
| Date range | Oct 2022 → Apr 2026 |
| Raw play events | 52,192 |
| Clean play events | 23,826 |
| Junk rows removed | 28,366 (54% of raw) |
| Total hours listened | 1,062 h |
| Unique artists | 1,171 |
| Unique tracks | 4,092 |
| Unique albums | 2,834 |
| Countries | DE (14,070 streams) · PK (9,740) · US (15) |
| Overall skip rate | 47.1% |
| Top artist | Pritam (68.6 h) |

> Raw data is not committed to this repo as it contains personal
> information. To reproduce: request your own data export from
> Spotify → Settings → Privacy → Download your data.

---

## Key findings

### Listening overview
1,062 hours of music across 5 years. 54% of raw events were filtered
out as junk which included accidental taps, sub-5-second plays, and app load
events.

### Top artist — Pritam (68.6 hours, 1,426 streams)
Pritam dominates by a wide margin in both countries, but with
strikingly different skip rates: 62.7% in Germany vs 46.5% in
Pakistan.

### Most loved track — "Kiya Hai Jo Pyar" by Mala
226 plays · 100% completion rate · 12.66 total hours.
Every single play was listened to in full.

### Germany vs Pakistan — two listening lives

| Metric | Germany (DE) | Pakistan (PK) |
|--------|-------------|----------------|
| Streams | 14,070 | 9,740 |
| Hours | 600.1 h | 461.5 h |
| Skip rate | 52.0% | 40.0% |
| Shuffle rate | 5.0% | 8.5% |
| Peak hour | 16:00 | 13:00 |
| Unique artists | 961 | 571 |

68% more artists discovered in Germany but with lower per-track
commitment, broader exploration and higher skip rate.

Qari Waheed Zafar Qasmi appears in the Pakistan top 8 but not Germany,
suggesting devotional listening stayed in Pakistan.

### Listening grew year over year — then peaked

| Year | Streams | Hours | Skip rate | Shuffle |
|------|---------|-------|-----------|---------|
| 2022 | 934 | 38.6 h | 50.0% | 0.1% |
| 2023 | 3,748 | 156.7 h | 42.6% | 5.8% |
| 2024 | 6,221 | 312.1 h | 39.2% | 14.9% |
| 2025 | 12,110 | 516.7 h | 52.6% | 3.2% |
| 2026 | 813 | 38.4 h | 42.8% | 0.0% |

2024 was peak shuffle (14.9%), an exploratory phase.

2025 was peak volume but also peak skipping. 

2026 shows the most intentional listening: 0% shuffle, lower skip rate.

### Weather and listening

**Germany - heat drives listening more than rain:**
Summer hot days (27°C+) averaged 3.92 hours/day - the highest of
any weather group.

Rainy days in Berlin did not produce more listening - dry summer days had higher stream counts. Heat appears
to be the driver, not precipitation.

**Pakistan - rain drives listening:**
Rainy monsoon days averaged 1.21 hours/day vs 0.77 on dry days.

Karachi monsoon rain (heavy, keeps you indoors) behaves differently
to Berlin summer rain (brief, mild).

**Country effect dominates weather effect:**
Skip rate in Pakistan (35–43%) stays consistently lower than Germany
(49–62%) across all weather conditions — where you are matters more
than what the weather is doing.

### Hidden gems
Tracks played rarely but always heard in full - "Alag Aasmaan" by
Anuv Jain (13 plays, 100% completion) and "Gul" by Anuv Jain (7 plays, 0% skip rate). 

---

## Data pipeline

```
Streaming_History_Audio_*.json  (multiple files, 2022–2026)
        ↓
  src/ingest.py
  · Merges all files, renames columns to snake_case
  · Drops podcasts, audiobooks, plays under 5 seconds
  · Derives time columns: hour, day, week, month, year, is_weekend
  · Extracts country and platform from raw fields
  · Drops ip_addr for privacy
  · Raw: 52,192 rows → Clean: 23,826 rows
  · Output: data/processed/streaming_clean.parquet
        ↓
  src/database.py
  · Builds star schema in DuckDB
  · dim_artists (1,171 rows)
  · dim_tracks  (4,092 rows)
  · dim_date    (23,826 rows — one per stream event)
  · fact_streams (23,826 rows)
  · Runs 5 validation checks before closing
  · Output: data/processed/spotify.duckdb
        ↓
  src/enrich.py
  · Calls Spotify API sp.tracks() for popularity, duration, release year
  · Derives behavioural features from listening history:
      - completion_rate         : avg % of track actually heard
      - skip_rate               : % of plays ended by skipping
      - shuffle_rate            : % of plays via shuffle
      - avg_plays_per_active_day: replay intensity
  · Note: Spotify deprecated audio_features for new apps in 2024
  · Output: dim_track_metadata added to spotify.duckdb
        ↓
  src/weather.py
  · Fetches historical daily weather from Open-Meteo (free, no API key required)
  · Berlin (DE) weather for DE listening days
  · Karachi (PK) weather for PK listening days
  · Only fetches weather for dates confirmed by conn_country
  · Derives: is_rainy, temp_category, season
  · Output: dim_weather added to spotify.duckdb
        ↓
  src/queries.py
  · 12 analytical SQL functions returning pandas DataFrames
  · No SQL in the dashboard, all queries live here
        ↓
  dashboard/app.py
  · 5-page Streamlit dashboard
  · Plotly charts throughout
  · Deployed: https://my-spotify-analysis.streamlit.app/
```

---

## Data model

Star schema in DuckDB:

```
dim_artists          dim_tracks           dim_date
───────────          ──────────           ────────
artist_id (PK)       track_id (PK)        date_id (PK)
artist_name          track_name           played_at
                     album_name           date
                     artist_id (FK)       year
                     track_uri            month
                                          day_of_week
                                          hour
                                          is_weekend

dim_track_metadata   dim_weather
──────────────────   ───────────
track_id (PK)        date
popularity           country
duration_ms          temp_mean
explicit             precipitation
release_year         sunshine_hrs
completion_rate      is_rainy
skip_rate            season
shuffle_rate         temp_category

                                      
                     fact_streams
                     ────────────
                     stream_id (PK)
                     played_at
                     ms_played
                     minutes_played
                     skipped
                     shuffle
                     offline
                     reason_start
                     reason_end
                     country
                     platform_group
                     track_id (FK)
                     artist_id (FK)
                     date_id (FK)
```

---

## Analytical queries

12 SQL functions in `src/queries.py`, each returning a clean DataFrame:

| Query | What it answers |
|-------|----------------|
| `get_summary_stats` | Headline KPIs across the full dataset |
| `get_top_artists` | Top N artists by hours (not play count) |
| `get_top_tracks` | Top N tracks by plays + completion rate |
| `get_hourly_heatmap` | Stream count for every hour × day of week |
| `get_monthly_trend` | Listening hours and skip rate per month |
| `get_year_comparison` | Year-over-year streams, hours, skip, shuffle |
| `get_skip_analysis` | Skip rate by year and country |
| `get_completion_leaders` | Tracks listened to fully, consistently |
| `get_hidden_gems` | Low plays, high completion, low skip |
| `get_listening_by_country` | Full behavioural profile: DE vs PK |
| `get_weather_listening` | Listening intensity by season + temperature |
| `get_rainy_vs_dry` | Rainy vs dry day comparison per country |

Hours used instead of play count for artist ranking as a 3-minute
skip inflates play count but contributes almost nothing to hours,
making hours the more honest engagement metric.

---

## Engineering decisions

**Spotify API deprecation**
The `audio_features` endpoint is restricted for new developer apps
as of late 2024. The project pivots to `sp.tracks()` for API
metadata and derives behavioural features (completion rate, skip
rate, replay intensity) directly from listening history — arguably
more meaningful than generic audio fingerprints because they reflect
personal response to each track.

**Why DuckDB**
DuckDB is a file-based analytical database optimised for columnar
aggregation queries. Zero server setup, full SQL support, and native parquet integration. The entire
warehouse is a single portable file.

**Star schema over a flat table**
Separating dimensions from facts keeps SQL clean, avoids data
repetition, and mirrors how real data warehouses are built. The
`dim_date` table enables fast time-based slicing without re-parsing
timestamps on every query.

**54% of raw data removed in cleaning**
Filtering sub-5-second plays
gives a dataset that reflects genuine listening intent.

**Weather only for confirmed country dates**
Weather is fetched per city but only joined for dates where
`conn_country` confirms you were in that country. Berlin weather
is never assigned to a Karachi day and vice versa.

---

## Setup

```bash
git clone https://github.com/unaizaafridi/my-spotify-analysis.git
cd my-spotify-analysis

python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Fill in your Spotify API credentials in .env
```

---

## How to run locally

```bash
# 1. Add your Spotify JSON export files to data/raw/

# 2. Run the pipeline in order
python src/ingest.py
python src/database.py
python src/enrich.py
python src/weather.py

# 3. Preview all queries
python src/queries.py

# 4. Launch the dashboard
streamlit run dashboard/app.py
```

---

## Tech stack

| Layer | Tool |
|-------|------|
| Language | Python 3.11 |
| Data processing | pandas, pyarrow |
| Warehouse | DuckDB |
| API enrichment | Spotify Web API, spotipy |
| Weather data | Open-Meteo (free, no API key) |
| Dashboard | Streamlit, Plotly |
| Deployment | Streamlit Community Cloud |
| Version control | Git, GitHub |

---

## Project structure

```
my-spotify-analysis/
├── data/
│   ├── raw/           ← Spotify JSON export (git-ignored, personal data)
│   └── processed/     ← spotify.duckdb warehouse
├── src/
│   ├── ingest.py      ← Parse & clean streaming history
│   ├── database.py    ← DuckDB star schema
│   ├── enrich.py      ← Spotify API + behavioural features
│   ├── weather.py     ← Historical weather from Open-Meteo
│   └── queries.py     ← 12 analytical SQL functions
├── dashboard/
│   └── app.py         ← 5-page Streamlit dashboard
├── .streamlit/
│   └── config.toml    ← Dark theme config
├── .env               ← Credentials template
├── requirements.txt
└── README.md
```

---