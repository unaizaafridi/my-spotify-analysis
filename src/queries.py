"""
src/queries.py
─────────────────────────────────────────────────────────────────────────────
Step 4 — Analytical queries powering the dashboard
─────────────────────────────────────────────────────────────────────────────
Each function:
  - accepts a DuckDB connection object
  - returns a clean pandas DataFrame
  - is self-contained and independently testable

The dashboard (app.py) imports and calls these functions directly —
no SQL lives in the dashboard code.

Run standalone to preview all results:
    python src/queries.py
"""

import duckdb
import pandas as pd
from pathlib import Path

# ── Path ───────────────────────────────────────────────────────────────────────
PROCESSED_DIR = Path("data/processed")
DB_FILE       = PROCESSED_DIR / "spotify.duckdb"


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return a read-only connection to the warehouse."""
    return duckdb.connect(str(DB_FILE), read_only=True)


# ─────────────────────────────────────────────────────────────────────────────
# 1. SUMMARY STATS
# Headline KPIs shown at the top of the dashboard.
# ─────────────────────────────────────────────────────────────────────────────
def get_summary_stats(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """
    Returns one row with top-level numbers across the entire dataset:
    - total_streams    : every play event that survived cleaning
    - total_hours      : sum of minutes_played converted to hours
    - unique_artists   : distinct artists ever played
    - unique_tracks    : distinct tracks ever played
    - overall_skip_pct : percentage of plays ended by skipping
    - shuffle_pct      : percentage of plays started via shuffle
    - years_covered    : how many calendar years the data spans
    - top_country      : which conn_country has the most streams
    """
    return con.execute("""
        SELECT
            COUNT(*)                                        AS total_streams,
            ROUND(SUM(minutes_played) / 60, 1)             AS total_hours,
            COUNT(DISTINCT artist_id)                       AS unique_artists,
            COUNT(DISTINCT track_id)                        AS unique_tracks,
            ROUND(AVG(skipped::INT)  * 100, 1)             AS overall_skip_pct,
            ROUND(AVG(shuffle::INT)  * 100, 1)             AS shuffle_pct,
            COUNT(DISTINCT YEAR(played_at))                 AS years_covered,

            -- Subquery to find the country with the most streams
            (
                SELECT country
                FROM fact_streams
                GROUP BY country
                ORDER BY COUNT(*) DESC
                LIMIT 1
            )                                               AS top_country
        FROM fact_streams
    """).df()


# ─────────────────────────────────────────────────────────────────────────────
# 2. TOP ARTISTS
# Ranks artists by total hours listened.
# Hours is more honest: a 3-minute skip inflates play count
# ─────────────────────────────────────────────────────────────────────────────
def get_top_artists(
    con: duckdb.DuckDBPyConnection,
    n: int = 15
) -> pd.DataFrame:
    """
    Top N artists by total hours listened.
    Also includes stream count and skip rate per artist
    so we can see whether high play counts reflect genuine
    engagement or just a high skip-through rate.
    """
    return con.execute(f"""
        SELECT
            a.artist_name,

            -- Total hours this artist was actually listened to
            ROUND(SUM(f.minutes_played) / 60, 1)           AS hours_listened,

            -- Raw play count (includes skips)
            COUNT(*)                                        AS total_streams,

            -- What % of plays on this artist were skipped
            ROUND(AVG(f.skipped::INT) * 100, 1)            AS skip_pct,

            -- How many unique tracks of theirs you've played
            COUNT(DISTINCT f.track_id)                      AS unique_tracks

        FROM fact_streams f
        JOIN dim_artists a ON f.artist_id = a.artist_id
        GROUP BY a.artist_name
        ORDER BY hours_listened DESC
        LIMIT {n}
    """).df()


# ─────────────────────────────────────────────────────────────────────────────
# 3. TOP TRACKS
# Ranks tracks by total plays, enriched with completion rate
# Minimum 3 plays filter removes one-off listens that skew completion rate.
# ─────────────────────────────────────────────────────────────────────────────
def get_top_tracks(
    con: duckdb.DuckDBPyConnection,
    n: int = 15
) -> pd.DataFrame:
    """
    Top N tracks by total play count.
    Joined with dim_track_metadata for completion rate —
    a track played 50 times at 20% completion tells a different
    story than one played 50 times at 95% completion.
    """
    return con.execute(f"""
        SELECT
            t.track_name,
            a.artist_name,

            -- How many times this track appeared in listening history
            COUNT(*)                                        AS total_plays,

            -- Average % of the track actually heard
            ROUND(m.completion_rate * 100, 1)              AS completion_pct,

            -- Skip rate for this specific track
            ROUND(AVG(f.skipped::INT) * 100, 1)            AS skip_pct,

            -- Total hours spent on this track
            ROUND(SUM(f.minutes_played) / 60, 2)           AS hours_listened

        FROM fact_streams f
        JOIN dim_tracks          t  ON f.track_id  = t.track_id
        JOIN dim_artists         a  ON f.artist_id = a.artist_id
        LEFT JOIN dim_track_metadata m ON f.track_id = m.track_id

        GROUP BY t.track_name, a.artist_name, m.completion_rate
        HAVING COUNT(*) >= 3
        ORDER BY total_plays DESC
        LIMIT {n}
    """).df()


# ─────────────────────────────────────────────────────────────────────────────
# 4. HOURLY HEATMAP
# Counts streams for every combination of hour (0–23) and
# day of week (Mon–Sun). Used to draw the heatmap chart —
# darker cells = more listening at that hour/day combination.
# ─────────────────────────────────────────────────────────────────────────────
def get_hourly_heatmap(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """
    Returns a 24 × 7 grid: stream count for each hour × day_of_week.
    Day order is Monday → Sunday to match a standard weekly calendar.
    """
    return con.execute("""
        SELECT
            d.hour,
            d.day_of_week,

            -- Total streams in this hour/day slot across all years
            COUNT(*)                                        AS stream_count

        FROM fact_streams f
        JOIN dim_date d ON f.date_id = d.date_id
        GROUP BY d.hour, d.day_of_week

        -- Order days Monday → Sunday for correct chart axis ordering
        ORDER BY
            CASE d.day_of_week
                WHEN 'Monday'    THEN 1
                WHEN 'Tuesday'   THEN 2
                WHEN 'Wednesday' THEN 3
                WHEN 'Thursday'  THEN 4
                WHEN 'Friday'    THEN 5
                WHEN 'Saturday'  THEN 6
                WHEN 'Sunday'    THEN 7
            END,
            d.hour
    """).df()


# ─────────────────────────────────────────────────────────────────────────────
# 5. MONTHLY TREND
# Aggregates total listening hours per calendar month across all years.
# Shows the rise and fall of listening intensity over time.
# ─────────────────────────────────────────────────────────────────────────────
def get_monthly_trend(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """
    Monthly listening hours from Oct 2022 → Apr 2026.
    Returns year, month number, month name, and hours listened that month.
    """
    return con.execute("""
        SELECT
            d.year,
            d.month,
            d.month_name,

            -- Hours listened in this specific year-month
            ROUND(SUM(f.minutes_played) / 60, 1)           AS hours_listened,

            -- Stream count for secondary axis if needed
            COUNT(*)                                        AS stream_count,

            -- Skip rate that month — does engagement change seasonally?
            ROUND(AVG(f.skipped::INT) * 100, 1)            AS skip_pct

        FROM fact_streams f
        JOIN dim_date d ON f.date_id = d.date_id
        GROUP BY d.year, d.month, d.month_name
        ORDER BY d.year, d.month
    """).df()


# ─────────────────────────────────────────────────────────────────────────────
# 6. YEAR-OVER-YEAR COMPARISON
# Side-by-side stats for each calendar year.
# The clearest way to show growth in listening and changes in behaviour —
# ─────────────────────────────────────────────────────────────────────────────
def get_year_comparison(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """
    One row per year with streams, hours, unique artists,
    unique tracks, skip rate and shuffle rate.
    """
    return con.execute("""
        SELECT
            d.year,
            COUNT(*)                                        AS total_streams,
            ROUND(SUM(f.minutes_played) / 60, 1)           AS total_hours,
            COUNT(DISTINCT f.artist_id)                     AS unique_artists,
            COUNT(DISTINCT f.track_id)                      AS unique_tracks,
            ROUND(AVG(f.skipped::INT)  * 100, 1)           AS skip_pct,
            ROUND(AVG(f.shuffle::INT)  * 100, 1)           AS shuffle_pct

        FROM fact_streams f
        JOIN dim_date d ON f.date_id = d.date_id
        GROUP BY d.year
        ORDER BY d.year
    """).df()


# ─────────────────────────────────────────────────────────────────────────────
# 7. SKIP ANALYSIS
# Breaks down skip behaviour in two ways:
#   a) by year  — did you become more or less selective over time?
#   b) by country — did location affect how much you skipped?
# ─────────────────────────────────────────────────────────────────────────────
def get_skip_analysis(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """
    Skip rate broken down by year AND country simultaneously.
    Reveals whether skipping behaviour changed over time.
    """
    return con.execute("""
        SELECT
            d.year,
            f.country,
            COUNT(*)                                        AS total_streams,

            -- Streams that ended because the user skipped
            SUM(f.skipped::INT)                            AS skipped_count,

            -- Percentage skipped
            ROUND(AVG(f.skipped::INT) * 100, 1)           AS skip_pct,

            -- Average minutes actually played per stream
            -- Lower = skipping earlier into the track
            ROUND(AVG(f.minutes_played), 2)                AS avg_mins_played

        FROM fact_streams f
        JOIN dim_date d ON f.date_id = d.date_id
        WHERE f.country IN ('DE', 'PK')     -- focus on the two main countries
        GROUP BY d.year, f.country
        ORDER BY d.year, f.country
    """).df()


# ─────────────────────────────────────────────────────────────────────────────
# 8. COMPLETION LEADERS
# Tracks you listen to all the way through, consistently.
# Minimum 5 plays filter ensures statistical reliability.
# ─────────────────────────────────────────────────────────────────────────────
def get_completion_leaders(
    con: duckdb.DuckDBPyConnection,
    n: int = 15
) -> pd.DataFrame:
    """
    Top N tracks by completion rate (minimum 5 plays).
    These are your most genuinely loved tracks.
    """
    return con.execute(f"""
        SELECT
            t.track_name,
            a.artist_name,
            ROUND(m.completion_rate * 100, 1)              AS completion_pct,
            m.total_plays,
            ROUND(AVG(f.minutes_played), 2)                AS avg_mins_played

        FROM dim_track_metadata m
        JOIN dim_tracks          t  ON m.track_id  = t.track_id
        JOIN dim_artists         a  ON t.artist_id = a.artist_id
        JOIN fact_streams        f  ON f.track_id  = m.track_id

        WHERE m.total_plays >= 5
          AND m.completion_rate IS NOT NULL

        GROUP BY
            t.track_name,
            a.artist_name,
            m.completion_rate,
            m.total_plays

        ORDER BY m.completion_rate DESC, m.total_plays DESC
        LIMIT {n}
    """).df()


# ─────────────────────────────────────────────────────────────────────────────
# 9. HIDDEN GEMS
# Tracks with a low overall play count but a very high completion rate.
# Play count between 3–15 keeps it genuinely "hidden" (not just new).
# ─────────────────────────────────────────────────────────────────────────────
def get_hidden_gems(
    con: duckdb.DuckDBPyConnection,
    n: int = 15
) -> pd.DataFrame:
    """
    Low play count (3–15) but high completion rate (>=90%).
    Tracks you don't play often but always listen to fully —
    the quiet favourites buried in your library.
    """
    return con.execute(f"""
        SELECT
            t.track_name,
            a.artist_name,
            m.total_plays,
            ROUND(m.completion_rate * 100, 1)              AS completion_pct,

            -- Skip rate should be near 0 for genuine hidden gems
            ROUND(m.skip_rate * 100, 1)                    AS skip_pct

        FROM dim_track_metadata m
        JOIN dim_tracks  t ON m.track_id  = t.track_id
        JOIN dim_artists a ON t.artist_id = a.artist_id

        WHERE m.total_plays BETWEEN 3 AND 15
          AND m.completion_rate >= 0.90
          AND m.skip_rate       <= 0.10

        ORDER BY m.completion_rate DESC, m.total_plays DESC
        LIMIT {n}
    """).df()


# ─────────────────────────────────────────────────────────────────────────────
# 10. LISTENING BY COUNTRY (DE vs PK)
# Compares your full listening profile between the two countries
# the same person, two different countries, two different listening lives.
# ─────────────────────────────────────────────────────────────────────────────
def get_listening_by_country(con: duckdb.DuckDBPyConnection) -> dict:
    """
    Returns a dict with three DataFrames:
      - 'summary'     : high-level stats per country
      - 'top_artists' : top 8 artists in each country
      - 'peak_hours'  : the 3 busiest listening hours per country
    """

    # -- Overall summary per country ------------------------------------------
    # Gives us the headline numbers to compare DE vs PK side by side
    summary = con.execute("""
        SELECT
            f.country,
            COUNT(*)                                        AS total_streams,
            ROUND(SUM(f.minutes_played) / 60, 1)           AS total_hours,
            COUNT(DISTINCT f.artist_id)                     AS unique_artists,
            COUNT(DISTINCT f.track_id)                      AS unique_tracks,
            ROUND(AVG(f.skipped::INT)  * 100, 1)           AS skip_pct,
            ROUND(AVG(f.shuffle::INT)  * 100, 1)           AS shuffle_pct,

            -- Most active hour in this country (mode of hour column)
            -- tells us when during the day listening peaked
            (
                SELECT d2.hour
                FROM fact_streams f2
                JOIN dim_date d2 ON f2.date_id = d2.date_id
                WHERE f2.country = f.country
                GROUP BY d2.hour
                ORDER BY COUNT(*) DESC
                LIMIT 1
            )                                               AS peak_hour

        FROM fact_streams f
        WHERE f.country IN ('DE', 'PK')
        GROUP BY f.country
        ORDER BY total_streams DESC
    """).df()

    # -- Top 8 artists per country --------------------------------------------
    # Did your taste differ between Pakistan and Germany?
    # Comparing these two lists is one of the dashboard's best stories.
    top_artists = con.execute("""
        SELECT
            f.country,
            a.artist_name,
            ROUND(SUM(f.minutes_played) / 60, 1)           AS hours_listened,
            COUNT(*)                                        AS streams,
            ROUND(AVG(f.skipped::INT) * 100, 1)            AS skip_pct,

            -- Rank within each country by hours listened
            ROW_NUMBER() OVER (
                PARTITION BY f.country
                ORDER BY SUM(f.minutes_played) DESC
            )                                               AS country_rank

        FROM fact_streams f
        JOIN dim_artists a ON f.artist_id = a.artist_id
        WHERE f.country IN ('DE', 'PK')
        GROUP BY f.country, a.artist_name
        QUALIFY country_rank <= 8
        ORDER BY f.country, country_rank
    """).df()

    # -- Peak listening hours per country -------------------------------------
    # Are you an evening listener in both countries,
    # or does the pattern shift? (timezone, work schedule, lifestyle)
    peak_hours = con.execute("""
        SELECT
            f.country,
            d.hour,
            COUNT(*)                                        AS streams,

            -- Rank hours within each country
            ROW_NUMBER() OVER (
                PARTITION BY f.country
                ORDER BY COUNT(*) DESC
            )                                               AS hour_rank

        FROM fact_streams f
        JOIN dim_date d ON f.date_id = d.date_id
        WHERE f.country IN ('DE', 'PK')
        GROUP BY f.country, d.hour
        QUALIFY hour_rank <= 5
        ORDER BY f.country, hour_rank
    """).df()

    return {
        "summary":    summary,
        "top_artists": top_artists,
        "peak_hours": peak_hours,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Useful for checking output before wiring into the dashboard.
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":

    if not DB_FILE.exists():
        raise FileNotFoundError(
            f"Database not found at {DB_FILE}\n"
            "Run src/database.py and src/enrich.py first."
        )

    con = get_connection()
    sep = "\n" + "─" * 68

    print(sep)
    print("  1. Summary stats")
    print(sep)
    print(get_summary_stats(con).to_string(index=False))

    print(sep)
    print("  2. Top 10 artists by hours")
    print(sep)
    print(get_top_artists(con, n=10).to_string(index=False))

    print(sep)
    print("  3. Top 10 tracks by plays")
    print(sep)
    print(get_top_tracks(con, n=10).to_string(index=False))

    print(sep)
    print("  4. Hourly heatmap (sample — Mon rows)")
    print(sep)
    heatmap = get_hourly_heatmap(con)
    print(heatmap[heatmap["day_of_week"] == "Monday"].to_string(index=False))

    print(sep)
    print("  5. Monthly trend (last 6 months)")
    print(sep)
    print(get_monthly_trend(con).tail(6).to_string(index=False))

    print(sep)
    print("  6. Year-over-year comparison")
    print(sep)
    print(get_year_comparison(con).to_string(index=False))

    print(sep)
    print("  7. Skip analysis by year + country")
    print(sep)
    print(get_skip_analysis(con).to_string(index=False))

    print(sep)
    print("  8. Completion leaders (top 8)")
    print(sep)
    print(get_completion_leaders(con, n=8).to_string(index=False))

    print(sep)
    print("  9. Hidden gems")
    print(sep)
    print(get_hidden_gems(con, n=8).to_string(index=False))

    print(sep)
    print("  10. Listening by country — summary")
    print(sep)
    country_data = get_listening_by_country(con)
    print("\n  Summary:")
    print(country_data["summary"].to_string(index=False))
    print("\n  Top artists per country:")
    print(country_data["top_artists"].to_string(index=False))
    print("\n  Peak hours per country:")
    print(country_data["peak_hours"].to_string(index=False))

    con.close()