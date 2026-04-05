"""
src/weather.py
─────────────────────────────────────────────────────────────────────────────
Step 3b — Fetch historical weather data from Open-Meteo (no API key)
─────────────────────────────────────────────────────────────────────────────
Fetches daily weather for the exact city you were in on each date,
determined by conn_country in your listening history:
  - Pakistan (PK) → Karachi  (24.8607° N, 67.0011° E)
  - Germany  (DE) → Berlin   (52.5200° N, 13.4050° E)

Weather variables fetched per day:
  - temperature_2m_max    : max temp in °C
  - temperature_2m_min    : min temp in °C
  - temperature_2m_mean   : mean temp in °C
  - precipitation_sum     : total rainfall in mm
  - sunshine_duration     : sunshine hours
  - windspeed_10m_max     : max wind speed km/h

Derived columns added:
  - is_rainy  : precipitation_sum > 1mm
  - season    : Winter / Spring / Summer / Autumn (hemisphere-aware)

Input  : data/processed/spotify.duckdb  (fact_streams, dim_date)
Output : data/processed/spotify.duckdb  (adds dim_weather table)

Run    : python src/weather.py
"""

import requests
import duckdb
import pandas as pd
from pathlib import Path
from datetime import datetime

# ── Paths ──────────────────────────────────────────────────────────────────────
PROCESSED_DIR = Path("data/processed")
DB_FILE       = PROCESSED_DIR / "spotify.duckdb"

if not DB_FILE.exists():
    raise FileNotFoundError(
        f"Could not find {DB_FILE}\n"
        "Run src/database.py first."
    )

# ── City coordinates ───────────────────────────────────────────────────────────
# We map each country to its primary city for weather lookup
CITY_COORDS = {
    "PK": {"city": "Karachi",  "lat": 24.8607, "lon": 67.0011},
    "DE": {"city": "Berlin",   "lat": 52.5200, "lon": 13.4050},
}

# ── Connect to DuckDB ──────────────────────────────────────────────────────────
con = duckdb.connect(str(DB_FILE))
print(f"Connected to database → {DB_FILE}")

# ── Drop existing weather table if rebuilding ──────────────────────────────────
con.execute("DROP TABLE IF EXISTS dim_weather")

# ── Get the date range per country from actual listening history ───────────────
# We only fetch weather for dates + countries where you actually listened
date_ranges = con.execute("""
    SELECT
        f.country,
        MIN(d.date)  AS start_date,
        MAX(d.date)  AS end_date,
        COUNT(DISTINCT d.date) AS active_days
    FROM fact_streams f
    JOIN dim_date d ON f.date_id = d.date_id
    WHERE f.country IN ('DE', 'PK')
    GROUP BY f.country
    ORDER BY f.country
""").df()

print("\nDate ranges to fetch weather for:")
print(date_ranges.to_string(index=False))

# ── Open-Meteo API fetcher ─────────────────────────────────────────────────────
OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"

WEATHER_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "precipitation_sum",
    "sunshine_duration",    # in seconds, we convert to hours
    "wind_speed_10m_max",
]

def fetch_weather(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    city: str,
    country: str,
) -> pd.DataFrame:
    """
    Calls Open-Meteo historical archive API for a given location and
    date range. Returns a DataFrame with one row per day.
    No API key required as Open-Meteo is fully open access.
    """
    params = {
        "latitude":        lat,
        "longitude":       lon,
        "start_date":      start_date,
        "end_date":        end_date,
        "daily":           ",".join(WEATHER_VARS),
        "timezone":        "auto",
        "wind_speed_unit": "kmh",
    }

    print(f"\n  Fetching {city} ({country}): {start_date} → {end_date}...")

    response = requests.get(OPEN_METEO_URL, params=params, timeout=30)

    if response.status_code != 200:
        raise ConnectionError(
            f"Open-Meteo API error {response.status_code}: {response.text}"
        )

    data  = response.json()
    daily = data.get("daily", {})

    if not daily:
        raise ValueError(f"No daily data returned for {city}")

    df = pd.DataFrame({
        "date":          pd.to_datetime(daily["time"]).date,
        "temp_max":      daily["temperature_2m_max"],
        "temp_min":      daily["temperature_2m_min"],
        "temp_mean":     daily["temperature_2m_mean"],
        "precipitation": daily["precipitation_sum"],
        "sunshine_hrs":  [
            round(s / 3600, 2) if s is not None else None
            for s in daily["sunshine_duration"]
        ],
        "wind_speed_max": daily["wind_speed_10m_max"],
    })

    # Add location identifiers
    df["country"] = country
    df["city"]    = city

    print(f"  Received {len(df):,} days of weather data ✓")
    return df


# ── Fetch weather for each country ─────────────────────────────────────────────
all_weather = []

for _, row in date_ranges.iterrows():
    country = row["country"]

    if country not in CITY_COORDS:
        print(f"  Skipping {country} — no coordinates defined")
        continue

    coords = CITY_COORDS[country]

    weather_df = fetch_weather(
        lat        = coords["lat"],
        lon        = coords["lon"],
        start_date = pd.Timestamp(row["start_date"]).strftime("%Y-%m-%d"),
        end_date   = pd.Timestamp(row["end_date"]).strftime("%Y-%m-%d"),
        city       = coords["city"],
        country    = country,
    )
    all_weather.append(weather_df)

# ── Combine all weather data ───────────────────────────────────────────────────
combined = pd.concat(all_weather, ignore_index=True)

# ── Derive helper columns ──────────────────────────────────────────────────────

# is_rainy: any day with more than 1mm precipitation counts as rainy
combined["is_rainy"] = combined["precipitation"] > 1.0

# temp_category: intuitive label for temperature range
def categorise_temp(temp):
    if temp is None:
        return "unknown"
    elif temp < 5:
        return "cold"
    elif temp < 15:
        return "cool"
    elif temp < 25:
        return "warm"
    else:
        return "hot"

combined["temp_category"] = combined["temp_mean"].apply(categorise_temp)

# season: hemisphere-aware
# Northern hemisphere (both Karachi and Berlin are northern)
# Winter: Dec, Jan, Feb | Spring: Mar, Apr, May
# Summer: Jun, Jul, Aug | Autumn: Sep, Oct, Nov
def get_season(date_val):
    month = pd.Timestamp(date_val).month
    if month in (12, 1, 2):
        return "Winter"
    elif month in (3, 4, 5):
        return "Spring"
    elif month in (6, 7, 8):
        return "Summer"
    else:
        return "Autumn"

combined["season"] = combined["date"].apply(get_season)

# Sort for cleanliness
combined = combined.sort_values(["country", "date"]).reset_index(drop=True)

# ── Filter to only dates where listening data confirms you were in that country
# This removes weather rows for dates where conn_country doesn't match
# e.g. removes Karachi weather for Nov 2024 dates when you were in Berlin
actual_dates = con.execute("""
    SELECT DISTINCT
        f.country,
        d.date
    FROM fact_streams f
    JOIN dim_date d ON f.date_id = d.date_id
    WHERE f.country IN ('DE', 'PK')
""").df()

actual_dates["date"] = pd.to_datetime(actual_dates["date"]).dt.date

before = len(combined)
combined = combined.merge(actual_dates, on=["country", "date"], how="inner")
after = len(combined)

print(f"\n  Filtered weather to confirmed listening dates: {before:,} → {after:,} rows")


# ── Save to DuckDB ─────────────────────────────────────────────────────────────
con.execute("CREATE TABLE dim_weather AS SELECT * FROM combined")
print(f"\nSaved dim_weather → {DB_FILE}")

# ── Validation ─────────────────────────────────────────────────────────────────
print("\n── Validation ───────────────────────────────────────────────────────")

total_rows = con.execute("SELECT COUNT(*) FROM dim_weather").fetchone()[0]
print(f"  Total weather rows     : {total_rows:,}")

per_country = con.execute("""
    SELECT country, city, COUNT(*) AS days, MIN(date) AS from_date, MAX(date) AS to_date
    FROM dim_weather
    GROUP BY country, city
    ORDER BY country
""").df()
print(per_country.to_string(index=False))

nulls = con.execute("""
    SELECT
        SUM(CASE WHEN temp_mean     IS NULL THEN 1 ELSE 0 END) AS null_temp,
        SUM(CASE WHEN precipitation IS NULL THEN 1 ELSE 0 END) AS null_precip,
        SUM(CASE WHEN sunshine_hrs  IS NULL THEN 1 ELSE 0 END) AS null_sunshine
    FROM dim_weather
""").df()
print(f"\n  Null check:")
print(nulls.to_string(index=False))

# ── Preview ────────────────────────────────────────────────────────────────────
print("\n── Weather summary by country and season ────────────────────────────")
seasonal = con.execute("""
    SELECT
        country,
        season,
        ROUND(AVG(temp_mean),     1)   AS avg_temp_c,
        ROUND(AVG(precipitation), 1)   AS avg_rain_mm,
        ROUND(AVG(sunshine_hrs),  1)   AS avg_sunshine_hrs,
        SUM(is_rainy::INT)             AS rainy_days,
        COUNT(*)                       AS total_days
    FROM dim_weather
    GROUP BY country, season
    ORDER BY country,
        CASE season
            WHEN 'Winter' THEN 1
            WHEN 'Spring' THEN 2
            WHEN 'Summer' THEN 3
            WHEN 'Autumn' THEN 4
        END
""").df()
print(seasonal.to_string(index=False))

print("\n── Listening hours vs weather (joined preview) ───────────────────────")
joined_preview = con.execute("""
    SELECT
        w.country,
        w.season,
        w.temp_category,
        COUNT(DISTINCT w.date)                          AS weather_days,
        COUNT(f.stream_id)                              AS total_streams,
        ROUND(SUM(f.minutes_played) / 60, 1)           AS hours_listened,
        ROUND(AVG(f.skipped::INT) * 100, 1)            AS skip_pct
    FROM dim_weather w
    JOIN dim_date d
        ON  w.date    = d.date
    JOIN fact_streams f
        ON  f.date_id  = d.date_id
        AND f.country  = w.country
    GROUP BY w.country, w.season, w.temp_category
    ORDER BY w.country, hours_listened DESC
""").df()
print(joined_preview.to_string(index=False))

con.close()
