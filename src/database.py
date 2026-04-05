"""
src/database.py
─────────────────────────────────────────────────────────────────────────────
Step 2 — Build DuckDB star schema warehouse
─────────────────────────────────────────────────────────────────────────────
Input  : data/processed/streaming_clean.parquet
Output : data/processed/spotify.duckdb

Run    : python src/database.py
"""

import duckdb
import pandas as pd
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
PROCESSED_DIR = Path("data/processed")
PARQUET_FILE  = PROCESSED_DIR / "streaming_clean.parquet"
DB_FILE       = PROCESSED_DIR / "spotify.duckdb"

if not PARQUET_FILE.exists():
    raise FileNotFoundError(
        f"Could not find {PARQUET_FILE}\n"
        "Run src/ingest.py first."
    )

# Remove existing DB so we always build fresh
if DB_FILE.exists():
    DB_FILE.unlink()

con = duckdb.connect(str(DB_FILE))
print(f"Created database → {DB_FILE}")

# ── Load parquet into staging with a unique row number from the start ─────────
con.execute(f"""
    CREATE TABLE staging AS
    SELECT
        ROW_NUMBER() OVER ()  AS row_id,
        *
    FROM read_parquet('{PARQUET_FILE.as_posix()}')
""")

total_rows = con.execute("SELECT COUNT(*) FROM staging").fetchone()[0]
print(f"Loaded {total_rows:,} rows into staging")

# ─────────────────────────────────────────────────────────────────────────────
# DIMENSION TABLES
# ─────────────────────────────────────────────────────────────────────────────

# ── dim_artists ───────────────────────────────────────────────────────────────
con.execute("""
    CREATE TABLE dim_artists AS
    SELECT
        ROW_NUMBER() OVER (ORDER BY artist_name)  AS artist_id,
        artist_name
    FROM (
        SELECT DISTINCT artist_name
        FROM staging
        WHERE artist_name IS NOT NULL
    )
""")

n_artists = con.execute("SELECT COUNT(*) FROM dim_artists").fetchone()[0]
print(f"  dim_artists   : {n_artists:,} rows")

# ── dim_tracks ────────────────────────────────────────────────────────────────
# Deduplicate on track_uri — take first occurrence of name/album per URI
con.execute("""
    CREATE TABLE dim_tracks AS
    SELECT
        ROW_NUMBER() OVER (ORDER BY track_name)   AS track_id,
        t.track_uri,
        t.track_name,
        t.album_name,
        a.artist_id
    FROM (
        SELECT DISTINCT ON (track_uri)
            track_uri,
            track_name,
            album_name,
            artist_name
        FROM staging
        WHERE track_uri IS NOT NULL
        ORDER BY track_uri, track_name
    ) t
    JOIN dim_artists a ON t.artist_name = a.artist_name
""")

n_tracks = con.execute("SELECT COUNT(*) FROM dim_tracks").fetchone()[0]
print(f"  dim_tracks    : {n_tracks:,} rows")

# ── dim_date ──────────────────────────────────────────────────────────────────
# One row per stream event using row_id — avoids duplicate timestamp problem
con.execute("""
    CREATE TABLE dim_date AS
    SELECT
        row_id        AS date_id,
        played_at,
        date,
        year,
        month,
        month_name,
        week,
        day_of_week,
        hour,
        is_weekend
    FROM staging
""")

n_dates = con.execute("SELECT COUNT(*) FROM dim_date").fetchone()[0]
print(f"  dim_date      : {n_dates:,} rows")

# ─────────────────────────────────────────────────────────────────────────────
# FACT TABLE
# ─────────────────────────────────────────────────────────────────────────────
# Join dim_date on row_id (1:1) — guarantees no fan-out duplicates

con.execute("""
    CREATE TABLE fact_streams AS
    SELECT
        s.row_id          AS stream_id,
        d.date_id,
        t.track_id,
        a.artist_id,
        s.played_at,
        s.ms_played,
        s.minutes_played,
        s.skipped,
        s.shuffle,
        s.offline,
        s.incognito_mode,
        s.reason_start,
        s.reason_end,
        s.country,
        s.platform_group
    FROM staging s
    JOIN dim_tracks  t ON s.track_uri   = t.track_uri
    JOIN dim_artists a ON s.artist_name = a.artist_name
    JOIN dim_date    d ON s.row_id      = d.date_id
    ORDER BY s.played_at
""")

n_fact = con.execute("SELECT COUNT(*) FROM fact_streams").fetchone()[0]
print(f"  fact_streams  : {n_fact:,} rows")

# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Validation ───────────────────────────────────────────────────────")

# Row count must match staging exactly
assert n_fact == total_rows, (
    f"Row count mismatch: staging={total_rows:,}, fact={n_fact:,}"
)
print(f"  Row count match        : {n_fact:,} = {total_rows:,} ✓")

# No orphaned track FKs
orphan_tracks = con.execute("""
    SELECT COUNT(*) FROM fact_streams f
    LEFT JOIN dim_tracks t ON f.track_id = t.track_id
    WHERE t.track_id IS NULL
""").fetchone()[0]
assert orphan_tracks == 0, f"Orphaned track_ids: {orphan_tracks}"
print(f"  Orphaned track FKs     : {orphan_tracks} ✓")

# No orphaned artist FKs
orphan_artists = con.execute("""
    SELECT COUNT(*) FROM fact_streams f
    LEFT JOIN dim_artists a ON f.artist_id = a.artist_id
    WHERE a.artist_id IS NULL
""").fetchone()[0]
assert orphan_artists == 0, f"Orphaned artist_ids: {orphan_artists}"
print(f"  Orphaned artist FKs    : {orphan_artists} ✓")

# No NULL stream_ids
null_ids = con.execute(
    "SELECT COUNT(*) FROM fact_streams WHERE stream_id IS NULL"
).fetchone()[0]
assert null_ids == 0, f"NULL stream_ids found: {null_ids}"
print(f"  NULL stream_ids        : {null_ids} ✓")

# dim_tracks has no duplicate URIs
dup_uris = con.execute("""
    SELECT COUNT(*) FROM (
        SELECT track_uri, COUNT(*) AS n
        FROM dim_tracks
        GROUP BY track_uri
        HAVING n > 1
    )
""").fetchone()[0]
assert dup_uris == 0, f"Duplicate track URIs in dim_tracks: {dup_uris}"
print(f"  Duplicate track URIs   : {dup_uris} ✓")

# ─────────────────────────────────────────────────────────────────────────────
# QUICK PREVIEW QUERIES
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Quick previews ───────────────────────────────────────────────────")

print("\n  Top 5 artists by total hours:")
top_artists = con.execute("""
    SELECT
        a.artist_name,
        ROUND(SUM(f.minutes_played) / 60, 1)  AS hours,
        COUNT(*)                               AS streams
    FROM fact_streams f
    JOIN dim_artists a ON f.artist_id = a.artist_id
    GROUP BY a.artist_name
    ORDER BY hours DESC
    LIMIT 5
""").df()
print(top_artists.to_string(index=False))

print("\n  Streams by year:")
by_year = con.execute("""
    SELECT
        d.year,
        COUNT(*)                               AS streams,
        ROUND(SUM(f.minutes_played) / 60, 1)  AS hours,
        ROUND(AVG(f.skipped::INT) * 100, 1)   AS skip_pct
    FROM fact_streams f
    JOIN dim_date d ON f.date_id = d.date_id
    GROUP BY d.year
    ORDER BY d.year
""").df()
print(by_year.to_string(index=False))

print("\n  Streams by country:")
by_country = con.execute("""
    SELECT
        country,
        COUNT(*)                               AS streams,
        ROUND(SUM(minutes_played) / 60, 1)    AS hours,
        ROUND(AVG(skipped::INT) * 100, 1)     AS skip_pct
    FROM fact_streams
    GROUP BY country
    ORDER BY streams DESC
""").df()
print(by_country.to_string(index=False))

# ── Drop staging — no longer needed ───────────────────────────────────────────
con.execute("DROP TABLE staging")

con.close()