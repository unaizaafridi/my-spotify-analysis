"""
src/ingest.py
─────────────────────────────────────────────────────────────────────────────
Step 1 — Parse & clean Spotify extended streaming history (2022–2026)
─────────────────────────────────────────────────────────────────────────────
Input  : data/raw/Streaming_History_Audio_*.json
Output : data/processed/streaming_clean.parquet

Run    : python src/ingest.py
"""

import json
import glob
import pandas as pd
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
RAW_DIR       = Path("data/raw")
PROCESSED_DIR = Path("data/processed")
OUTPUT_FILE   = PROCESSED_DIR / "streaming_clean.parquet"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# ── 1. Load all Streaming_History_Audio_*.json files ───────────────────────────
files = sorted(RAW_DIR.glob("Streaming_History_Audio_*.json"))

if not files:
    raise FileNotFoundError(
        f"No Streaming_History_Audio_*.json files found in {RAW_DIR}/\n"
        "Make sure your Spotify JSON export files are in data/raw/"
    )

print(f"Found {len(files)} file(s):")
raw_frames = []

for f in files:
    with open(f, encoding="utf-8") as fh:
        data = json.load(fh)
    df_chunk = pd.DataFrame(data)
    raw_frames.append(df_chunk)
    print(f"  {f.name}: {len(data):,} rows")

df = pd.concat(raw_frames, ignore_index=True)
print(f"\nTotal raw rows: {len(df):,}")

# ── 2. Rename columns to snake_case ───────────────────────────────────────────
df = df.rename(columns={
    "ts":                                "played_at",
    "ms_played":                         "ms_played",
    "platform":                          "platform",
    "conn_country":                      "country",
    "ip_addr":                           "ip_addr",
    "master_metadata_track_name":        "track_name",
    "master_metadata_album_artist_name": "artist_name",
    "master_metadata_album_album_name":  "album_name",
    "spotify_track_uri":                 "track_uri",
    "reason_start":                      "reason_start",
    "reason_end":                        "reason_end",
    "shuffle":                           "shuffle",
    "skipped":                           "skipped",
    "offline":                           "offline",
    "incognito_mode":                    "incognito_mode",
})

# ── 3. Keep only music rows, drop podcast/audiobook/episode columns ────────────
music_mask = df["track_name"].notna() & df["artist_name"].notna()
df = df[music_mask].copy()

drop_cols = [
    "episode_name", "episode_show_name", "spotify_episode_uri",
    "audiobook_title", "audiobook_uri",
    "audiobook_chapter_uri", "audiobook_chapter_title",
    "offline_timestamp", "ip_addr",          # ip_addr dropped here — privacy
]
df = df.drop(columns=[c for c in drop_cols if c in df.columns])

# ── 4. Fix types ───────────────────────────────────────────────────────────────
df["played_at"]      = pd.to_datetime(df["played_at"], utc=True)
df["ms_played"]      = pd.to_numeric(df["ms_played"], errors="coerce").fillna(0).astype(int)
df["shuffle"]        = df["shuffle"].fillna(False).astype(bool)
df["skipped"]        = df["skipped"].fillna(False).astype(bool)
df["offline"]        = df["offline"].fillna(False).astype(bool)
df["incognito_mode"] = df["incognito_mode"].fillna(False).astype(bool)
df["country"]        = df["country"].fillna("unknown").str.upper().str.strip()
df["platform"]       = df["platform"].fillna("unknown").str.lower().str.strip()

# Normalise platform into cleaner categories
platform_map = {
    "android":    "mobile",
    "ios":        "mobile",
    "web_player": "web",
    "desktop":    "desktop",
    "partner":    "other",
}
df["platform_group"] = df["platform"].map(platform_map).fillna("other")

# ── 5. Derive time columns ─────────────────────────────────────────────────────
df["minutes_played"] = (df["ms_played"] / 60_000).round(2)
df["date"]           = df["played_at"].dt.date
df["year"]           = df["played_at"].dt.year
df["month"]          = df["played_at"].dt.month
df["month_name"]     = df["played_at"].dt.strftime("%b")
df["week"]           = df["played_at"].dt.isocalendar().week.astype(int)
df["day_of_week"]    = df["played_at"].dt.day_name()
df["hour"]           = df["played_at"].dt.hour
df["is_weekend"]     = df["played_at"].dt.dayofweek >= 5

# ── 6. Extract track_id from URI ───────────────────────────────────────────────
# spotify:track:4SqPZorSDuUtvdJwVGeZRC  →  4SqPZorSDuUtvdJwVGeZRC
df["track_id"] = df["track_uri"].str.split(":").str[-1]

# ── 7. Remove junk rows ────────────────────────────────────────────────────────
before = len(df)

# Under 5 seconds = accidental tap, not a real listen
df = df[df["ms_played"] >= 5_000]

# Drop exact duplicates
df = df.drop_duplicates()

after  = len(df)
removed = before - after
print(f"Removed {removed:,} junk rows  →  {after:,} clean rows remaining")

# ── 8. Sort chronologically ────────────────────────────────────────────────────
df = df.sort_values("played_at").reset_index(drop=True)

# ── 9. Save ────────────────────────────────────────────────────────────────────
df.to_parquet(OUTPUT_FILE, index=False)
print(f"\nSaved → {OUTPUT_FILE}")

# ── 10. Sanity check printout ──────────────────────────────────────────────────
total_hours   = df["minutes_played"].sum() / 60
skip_rate     = df["skipped"].mean() * 100
shuffle_rate  = df["shuffle"].mean() * 100
offline_rate  = df["offline"].mean() * 100

print("\n── Dataset summary ──────────────────────────────────────────────────")
print(f"  Date range      : {df['played_at'].min().date()} → {df['played_at'].max().date()}")
print(f"  Years covered   : {sorted(df['year'].unique())}")
print(f"  Total hours     : {total_hours:,.1f} h")
print(f"  Total streams   : {len(df):,}")
print(f"  Unique artists  : {df['artist_name'].nunique():,}")
print(f"  Unique tracks   : {df['track_name'].nunique():,}")
print(f"  Unique albums   : {df['album_name'].nunique():,}")
print(f"  Skip rate       : {skip_rate:.1f}%")
print(f"  Shuffle rate    : {shuffle_rate:.1f}%")
print(f"  Offline rate    : {offline_rate:.1f}%")
print(f"\n── By year ──────────────────────────────────────────────────────────")
year_summary = (
    df.groupby("year")
    .agg(
        streams        = ("played_at",     "count"),
        hours          = ("minutes_played","sum"),
        unique_artists = ("artist_name",   "nunique"),
        unique_tracks  = ("track_name",    "nunique"),
        skip_rate      = ("skipped",       "mean"),
    )
    .assign(
        hours     = lambda x: (x["hours"] / 60).round(1),
        skip_rate = lambda x: (x["skip_rate"] * 100).round(1),
    )
)
print(year_summary.to_string())
print(f"\n── By country ───────────────────────────────────────────────────────")
print(df["country"].value_counts().head(10).to_string())
print(f"\n── By platform ──────────────────────────────────────────────────────")
print(df["platform_group"].value_counts().to_string())