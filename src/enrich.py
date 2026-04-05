"""
src/enrich.py
─────────────────────────────────────────────────────────────────────────────
Step 3 — Enrich tracks with Spotify API track metadata
─────────────────────────────────────────────────────────────────────────────
Note: Spotify deprecated the audio_features endpoint for new apps in 2024.
We use sp.tracks() instead which returns popularity, duration, release date
and explicit flag — all useful for analysis.

We also derive behavioural features from the listening history itself:
  - completion_rate         : avg % of track actually listened to
  - skip_rate               : % of plays that were skipped
  - shuffle_rate            : % of plays via shuffle
  - avg_plays_per_active_day: how often replayed on days it was played

Input  : data/processed/spotify.duckdb  (dim_tracks, fact_streams)
Output : data/processed/spotify.duckdb  (adds dim_track_metadata table)

Run    : python src/enrich.py
"""

import os
import time
import duckdb
import spotipy
import pandas as pd
from pathlib import Path
from tqdm import tqdm
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyClientCredentials

# ── Load credentials ───────────────────────────────────────────────────────────
load_dotenv()

SPOTIFY_CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
    raise EnvironmentError(
        "Missing Spotify credentials in .env\n"
        "Make sure .env contains:\n"
        "  SPOTIFY_CLIENT_ID=your_id_here\n"
        "  SPOTIFY_CLIENT_SECRET=your_secret_here"
    )

# ── Paths ──────────────────────────────────────────────────────────────────────
PROCESSED_DIR = Path("data/processed")
DB_FILE       = PROCESSED_DIR / "spotify.duckdb"

if not DB_FILE.exists():
    raise FileNotFoundError(
        f"Could not find {DB_FILE}\n"
        "Run src/database.py first."
    )

# ── Connect to Spotify API ─────────────────────────────────────────────────────
try:
    auth_manager = SpotifyClientCredentials(
        client_id     = SPOTIFY_CLIENT_ID,
        client_secret = SPOTIFY_CLIENT_SECRET,
    )
    sp = spotipy.Spotify(auth_manager=auth_manager)
    sp.search(q="test", limit=1)
    print("Spotify API connected ✓")
except Exception as e:
    raise ConnectionError(
        f"Could not connect to Spotify API: {e}\n"
        "Check your SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in .env"
    )

# ── Connect to DuckDB ──────────────────────────────────────────────────────────
con = duckdb.connect(str(DB_FILE))
print(f"Connected to database → {DB_FILE}")

# ── Fetch all unique tracks from dim_tracks ────────────────────────────────────
tracks_df = con.execute("""
    SELECT track_id, track_uri, track_name
    FROM dim_tracks
    WHERE track_uri IS NOT NULL
    ORDER BY track_id
""").df()

total_tracks = len(tracks_df)
print(f"Tracks to enrich: {total_tracks:,}")

# Extract Spotify track ID from URI
# spotify:track:4SqPZorSDuUtvdJwVGeZRC → 4SqPZorSDuUtvdJwVGeZRC
tracks_df["spotify_id"] = tracks_df["track_uri"].str.split(":").str[-1]

# ─────────────────────────────────────────────────────────────────────────────
# PART 1 — Fetch track metadata from Spotify API (sp.tracks)
# sp.tracks() still works for new apps unlike audio_features
# Returns: popularity, duration_ms, explicit, release_date
# ─────────────────────────────────────────────────────────────────────────────
BATCH_SIZE       = 50     # sp.tracks() max is 50
MAX_RETRIES      = 3
RETRY_DELAY      = 5
RATE_LIMIT_DELAY = 0.5

batches = [
    tracks_df.iloc[i : i + BATCH_SIZE]
    for i in range(0, total_tracks, BATCH_SIZE)
]

print(f"Fetching metadata in {len(batches)} batches of up to {BATCH_SIZE}...\n")

api_results  = []
failed_count = 0

for batch_df in tqdm(batches, desc="Fetching track metadata", unit="batch"):
    spotify_ids = batch_df["spotify_id"].tolist()
    track_ids   = batch_df["track_id"].tolist()

    tracks_data = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            tracks_data = sp.tracks(spotify_ids)
            time.sleep(RATE_LIMIT_DELAY)
            break
        except spotipy.exceptions.SpotifyException as e:
            if e.http_status == 429:
                wait = int(e.headers.get("Retry-After", 10))
                tqdm.write(f"  Rate limited. Waiting {wait}s...")
                time.sleep(wait)
            else:
                tqdm.write(f"  Spotify error (attempt {attempt}): {e}")
                time.sleep(RETRY_DELAY)
        except Exception as e:
            tqdm.write(f"  Error (attempt {attempt}): {e}")
            time.sleep(RETRY_DELAY)

    if tracks_data is None:
        failed_count += len(spotify_ids)
        for track_id in track_ids:
            api_results.append({
                "track_id":      track_id,
                "popularity":    None,
                "duration_ms":   None,
                "explicit":      None,
                "release_date":  None,
                "release_year":  None,
                "api_available": False,
            })
        continue

    for track_id, track in zip(track_ids, tracks_data["tracks"]):
        if track is None:
            api_results.append({
                "track_id":      track_id,
                "popularity":    None,
                "duration_ms":   None,
                "explicit":      None,
                "release_date":  None,
                "release_year":  None,
                "api_available": False,
            })
        else:
            release_date = track.get("album", {}).get("release_date", None)
            release_year = int(release_date[:4]) if release_date else None
            api_results.append({
                "track_id":      track_id,
                "popularity":    track.get("popularity"),
                "duration_ms":   track.get("duration_ms"),
                "explicit":      track.get("explicit"),
                "release_date":  release_date,
                "release_year":  release_year,
                "api_available": True,
            })

api_df = pd.DataFrame(api_results)

# Save API results first so duration_ms is available for completion_rate calc
con.execute("DROP TABLE IF EXISTS dim_track_metadata")
con.execute("CREATE TABLE dim_track_metadata AS SELECT * FROM api_df")

# ─────────────────────────────────────────────────────────────────────────────
# PART 2 — Derive behavioural features from listening history
# These are MORE personal than Spotify's audio features and unique to you
# ─────────────────────────────────────────────────────────────────────────────
print("\nDeriving behavioural features from listening history...")

behavioural_df = con.execute("""
    SELECT
        f.track_id,
        COUNT(*)                                             AS total_plays,
        ROUND(
            LEAST(
                AVG(f.ms_played::FLOAT /
                    NULLIF(m.duration_ms, 0)),
                1.0
            ), 3
        )                                                    AS completion_rate,
        ROUND(AVG(f.skipped::INT),  3)                      AS skip_rate,
        ROUND(AVG(f.shuffle::INT),  3)                      AS shuffle_rate,
        ROUND(
            COUNT(*) * 1.0 /
            NULLIF(COUNT(DISTINCT d.date), 0),
            2
        )                                                    AS avg_plays_per_active_day
    FROM fact_streams f
    JOIN dim_date d ON f.date_id = d.date_id
    LEFT JOIN dim_track_metadata m ON f.track_id = m.track_id
    GROUP BY f.track_id
""").df()

# ─────────────────────────────────────────────────────────────────────────────
# PART 3 — Merge API metadata + behavioural features and save final table
# ─────────────────────────────────────────────────────────────────────────────
final_df = api_df.merge(behavioural_df, on="track_id", how="left")

con.execute("DROP TABLE IF EXISTS dim_track_metadata")
con.execute("CREATE TABLE dim_track_metadata AS SELECT * FROM final_df")

print(f"Saved dim_track_metadata → {DB_FILE}")

# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Validation ───────────────────────────────────────────────────────")

total_saved = con.execute(
    "SELECT COUNT(*) FROM dim_track_metadata"
).fetchone()[0]

available = con.execute(
    "SELECT COUNT(*) FROM dim_track_metadata WHERE api_available = true"
).fetchone()[0]

coverage = (available / total_tracks * 100) if total_tracks > 0 else 0

print(f"  Total tracks in DB     : {total_tracks:,}")
print(f"  Metadata rows saved    : {total_saved:,}")
print(f"  API available          : {available:,}  ({coverage:.1f}%)")
print(f"  Not found in API       : {total_tracks - available:,}")
if failed_count:
    print(f"  Failed API calls       : {failed_count:,} tracks")

# ─────────────────────────────────────────────────────────────────────────────
# PREVIEWS
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Most popular tracks in your library (Spotify popularity 0–100) ──")
popular = con.execute("""
    SELECT
        t.track_name,
        a.artist_name,
        m.popularity,
        m.release_year,
        m.total_plays
    FROM dim_track_metadata m
    JOIN dim_tracks  t ON m.track_id  = t.track_id
    JOIN dim_artists a ON t.artist_id = a.artist_id
    WHERE m.api_available = true
    ORDER BY m.popularity DESC
    LIMIT 8
""").df()
print(popular.to_string(index=False))

print("\n── Tracks you complete most (highest completion rate, min 5 plays) ──")
completed = con.execute("""
    SELECT
        t.track_name,
        a.artist_name,
        ROUND(m.completion_rate * 100, 1)  AS completion_pct,
        m.total_plays
    FROM dim_track_metadata m
    JOIN dim_tracks  t ON m.track_id  = t.track_id
    JOIN dim_artists a ON t.artist_id = a.artist_id
    WHERE m.total_plays >= 5
      AND m.completion_rate IS NOT NULL
    ORDER BY m.completion_rate DESC
    LIMIT 8
""").df()
print(completed.to_string(index=False))

print("\n── Tracks you skip most (min 5 plays) ───────────────────────────────")
skipped = con.execute("""
    SELECT
        t.track_name,
        a.artist_name,
        ROUND(m.skip_rate * 100, 1)  AS skip_pct,
        m.total_plays
    FROM dim_track_metadata m
    JOIN dim_tracks  t ON m.track_id  = t.track_id
    JOIN dim_artists a ON t.artist_id = a.artist_id
    WHERE m.total_plays >= 5
    ORDER BY m.skip_rate DESC
    LIMIT 8
""").df()
print(skipped.to_string(index=False))

con.close()