"""
dashboard/app.py
─────────────────────────────────────────────────────────────────────────────
Step 5 — Streamlit dashboard
─────────────────────────────────────────────────────────────────────────────
Run: streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

# Allow imports from src/ when running from project root
sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from queries import (
    get_connection,
    get_summary_stats,
    get_top_artists,
    get_top_tracks,
    get_hourly_heatmap,
    get_monthly_trend,
    get_year_comparison,
    get_skip_analysis,
    get_completion_leaders,
    get_hidden_gems,
    get_listening_by_country,
    get_weather_listening,
    get_rainy_vs_dry,
)

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title = "Spotify Listening Analysis",
    page_icon  = "🎵",
    layout     = "wide",
)

# ── Colour constants ───────────────────────────────────────────────────────────
# Used consistently across all charts
DE_COLOUR     = "#7F77DD"   # purple  — Germany
PK_COLOUR     = "#1D9E75"   # teal    — Pakistan
ACCENT        = "#F0997B"   # coral   — highlights
NEUTRAL       = "#B4B2A9"   # gray    — secondary elements
BG_CARD       = "#1E1E2E"   # dark card background

COUNTRY_COLOURS = {"DE": DE_COLOUR, "PK": PK_COLOUR}
SEASON_COLOURS  = {
    "Winter": "#85B7EB",
    "Spring": "#97C459",
    "Summer": "#EF9F27",
    "Autumn": "#D85A30",
}

# ── Cached data loader ─────────────────────────────────────────────────────────
# st.cache_data means queries only run once per session — fast page switching
@st.cache_data
def load_all():
    con = get_connection()
    data = {
        "summary":         get_summary_stats(con),
        "top_artists":     get_top_artists(con, n=15),
        "top_tracks":      get_top_tracks(con, n=15),
        "heatmap":         get_hourly_heatmap(con),
        "monthly":         get_monthly_trend(con),
        "yearly":          get_year_comparison(con),
        "skip_analysis":   get_skip_analysis(con),
        "completion":      get_completion_leaders(con, n=15),
        "hidden_gems":     get_hidden_gems(con, n=15),
        "country":         get_listening_by_country(con),
        "weather":         get_weather_listening(con),
        "rainy_dry":       get_rainy_vs_dry(con),
    }
    con.close()
    return data

# ── Sidebar navigation ─────────────────────────────────────────────────────────
st.sidebar.title("🎵 My Spotify Analysis")
st.sidebar.markdown("Personal listening analysis · 2022–2026")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigate",
    [
        "Overview",
        "Time Patterns",
        "Engagement",
        "DE vs PK",
        "Weather",
    ],
    label_visibility = "collapsed",
)

st.sidebar.markdown("---")
st.sidebar.caption("Built with DuckDB · Streamlit · Plotly")

# ── Load data ──────────────────────────────────────────────────────────────────
with st.spinner("Loading data..."):
    d = load_all()

summary = d["summary"].iloc[0]

# ── Helper: metric card row ────────────────────────────────────────────────────
def metric_row(metrics: list):
    """
    Renders a row of st.metric cards.
    metrics = list of (label, value, delta) tuples. delta is optional.
    """
    cols = st.columns(len(metrics))
    for col, (label, value, *delta) in zip(cols, metrics):
        col.metric(label, value, delta[0] if delta else None)


# ═════════════════════════════════════════════════════════════════════════════
# PAGE 1 — OVERVIEW
# ═════════════════════════════════════════════════════════════════════════════
if page == "Overview":

    st.title("Listening overview")
    st.caption("4 years of Spotify data · Oct 2022 → Apr 2026")
    st.markdown("---")

    # ── KPI row ───────────────────────────────────────────────────────────────
    metric_row([
        ("Total hours",      f"{summary['total_hours']:,.0f} h",),
        ("Total streams",    f"{summary['total_streams']:,}",),
        ("Unique artists",   f"{summary['unique_artists']:,}",),
        ("Unique tracks",    f"{summary['unique_tracks']:,}",),
        ("Overall skip rate",f"{summary['overall_skip_pct']}%",),
        ("Top country",      summary["top_country"],),
    ])

    st.markdown("---")
    col1, col2 = st.columns([3, 2])

    # ── Top artists bar chart ─────────────────────────────────────────────────
    with col1:
        st.subheader("Top artists by hours listened")
        st.caption("Hours is a more honest metric than play count — a skip counts as a play but contributes almost nothing to hours.")

        fig = px.bar(
            d["top_artists"].head(12),
            x             = "hours_listened",
            y             = "artist_name",
            orientation   = "h",
            color         = "skip_pct",
            color_continuous_scale = "RdYlGn_r",
            labels        = {
                "hours_listened": "Hours",
                "artist_name":    "Artist",
                "skip_pct":       "Skip %",
            },
            hover_data    = ["total_streams", "unique_tracks"],
        )
        fig.update_layout(
            yaxis    = {"categoryorder": "total ascending"},
            height   = 440,
            margin   = {"l": 0, "r": 0, "t": 10, "b": 0},
            coloraxis_colorbar = {"title": "Skip %"},
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Top tracks table ──────────────────────────────────────────────────────
    with col2:
        st.subheader("Top tracks")
        st.caption("Ranked by play count · colour = completion rate")

        tracks_display = d["top_tracks"].head(12)[[
            "track_name", "artist_name", "total_plays", "completion_pct"
        ]].rename(columns={
            "track_name":     "Track",
            "artist_name":    "Artist",
            "total_plays":    "Plays",
            "completion_pct": "Completion %",
        })

        st.dataframe(
            tracks_display,
            use_container_width = True,
            height              = 440,
            hide_index          = True,
            column_config       = {
                "Completion %": st.column_config.ProgressColumn(
                    "Completion %",
                    min_value = 0,
                    max_value = 100,
                    format    = "%.0f%%",
                ),
            },
        )

    # ── Year-over-year summary bar ─────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Listening volume by year")

    yearly = d["yearly"]
    fig2 = go.Figure()

    fig2.add_trace(go.Bar(
        x    = yearly["year"],
        y    = yearly["total_hours"],
        name = "Hours listened",
        marker_color = DE_COLOUR,
        text = yearly["total_hours"].apply(lambda x: f"{x:.0f}h"),
        textposition = "outside",
    ))

    fig2.add_trace(go.Scatter(
        x    = yearly["year"],
        y    = yearly["skip_pct"],
        name = "Skip %",
        mode = "lines+markers",
        line = {"color": ACCENT, "width": 2.5},
        yaxis = "y2",
        marker = {"size": 8},
    ))

    fig2.update_layout(
        yaxis  = {"title": "Hours listened"},
        yaxis2 = {
            "title":    "Skip rate %",
            "overlaying": "y",
            "side":     "right",
            "range":    [0, 80],
        },
        legend  = {"orientation": "h", "y": 1.1},
        height  = 320,
        margin  = {"l": 0, "r": 0, "t": 20, "b": 0},
        barmode = "group",
    )
    st.plotly_chart(fig2, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
# PAGE 2 — TIME PATTERNS
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Time Patterns":

    st.title("Time patterns")
    st.caption("When do you listen — by hour, day, month, and year")
    st.markdown("---")

    # ── Heatmap ───────────────────────────────────────────────────────────────
    st.subheader("Listening heatmap — hour of day × day of week")
    st.caption("Darker = more streams in that hour/day slot across all years combined.")

    heatmap_df = d["heatmap"]
    day_order  = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

    pivot = heatmap_df.pivot(
        index   = "day_of_week",
        columns = "hour",
        values  = "stream_count",
    ).reindex(day_order)

    fig3 = px.imshow(
        pivot,
        color_continuous_scale = "Purples",
        labels = {"x": "Hour of day", "y": "Day", "color": "Streams"},
        aspect = "auto",
    )
    fig3.update_layout(
        height = 300,
        margin = {"l": 0, "r": 0, "t": 10, "b": 0},
        xaxis  = {"dtick": 1},
    )
    st.plotly_chart(fig3, use_container_width=True)

    st.markdown("---")
    col1, col2 = st.columns(2)

    # ── Monthly trend ─────────────────────────────────────────────────────────
    with col1:
        st.subheader("Monthly listening hours")
        st.caption("Across all years — shows seasonal patterns and life events.")

        monthly = d["monthly"].copy()
        monthly["period"] = monthly["year"].astype(str) + "-" + monthly["month"].astype(str).str.zfill(2)

        fig4 = go.Figure()
        fig4.add_trace(go.Scatter(
            x    = monthly["period"],
            y    = monthly["hours_listened"],
            mode = "lines+markers",
            line = {"color": DE_COLOUR, "width": 2},
            fill = "tozeroy",
            fillcolor = "rgba(127,119,221,0.15)",
            name = "Hours",
            hovertemplate = "%{x}<br>%{y:.1f} hours<extra></extra>",
        ))
        fig4.update_layout(
            height  = 300,
            margin  = {"l": 0, "r": 0, "t": 10, "b": 0},
            xaxis   = {"tickangle": -45},
            yaxis   = {"title": "Hours"},
            showlegend = False,
        )
        st.plotly_chart(fig4, use_container_width=True)

    # ── Skip rate by month ────────────────────────────────────────────────────
    with col2:
        st.subheader("Skip rate by month")
        st.caption("Does your patience change by season?")

        fig5 = go.Figure()
        fig5.add_trace(go.Scatter(
            x    = monthly["period"],
            y    = monthly["skip_pct"],
            mode = "lines+markers",
            line = {"color": ACCENT, "width": 2},
            fill = "tozeroy",
            fillcolor = "rgba(240,153,123,0.15)",
            name = "Skip %",
            hovertemplate = "%{x}<br>%{y:.1f}% skipped<extra></extra>",
        ))
        fig5.update_layout(
            height  = 300,
            margin  = {"l": 0, "r": 0, "t": 10, "b": 0},
            xaxis   = {"tickangle": -45},
            yaxis   = {"title": "Skip rate %"},
            showlegend = False,
        )
        st.plotly_chart(fig5, use_container_width=True)

    # ── Year comparison table ─────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Year-over-year breakdown")

    yearly_display = d["yearly"].rename(columns={
        "year":            "Year",
        "total_streams":   "Streams",
        "total_hours":     "Hours",
        "unique_artists":  "Artists",
        "unique_tracks":   "Tracks",
        "skip_pct":        "Skip %",
        "shuffle_pct":     "Shuffle %",
    })
    st.dataframe(yearly_display, use_container_width=True, hide_index=True)


# ═════════════════════════════════════════════════════════════════════════════
# PAGE 3 — ENGAGEMENT
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Engagement":

    st.title("Engagement analysis")
    st.caption("Skip rate, completion rate, hidden gems — beyond play counts")
    st.markdown("---")

    col1, col2 = st.columns(2)

    # ── Skip rate by year + country ───────────────────────────────────────────
    with col1:
        st.subheader("Skip rate — year × country")
        st.caption("Did you become more or less selective over time? Split by where you were living.")

        skip_df = d["skip_analysis"]
        fig6 = px.bar(
            skip_df,
            x         = "year",
            y         = "skip_pct",
            color     = "country",
            barmode   = "group",
            color_discrete_map = COUNTRY_COLOURS,
            labels    = {
                "skip_pct": "Skip rate %",
                "year":     "Year",
                "country":  "Country",
            },
            hover_data = ["total_streams", "avg_mins_played"],
        )
        fig6.update_layout(
            height = 320,
            margin = {"l": 0, "r": 0, "t": 10, "b": 0},
        )
        st.plotly_chart(fig6, use_container_width=True)

    # ── Completion leaders ─────────────────────────────────────────────────────
    with col2:
        st.subheader("Completion leaders")
        st.caption("Tracks you always listen to in full — minimum 5 plays.")

        comp_display = d["completion"].head(12)[[
            "track_name", "artist_name", "completion_pct", "total_plays"
        ]].rename(columns={
            "track_name":     "Track",
            "artist_name":    "Artist",
            "completion_pct": "Completion %",
            "total_plays":    "Plays",
        })
        st.dataframe(
            comp_display,
            use_container_width = True,
            height              = 320,
            hide_index          = True,
            column_config       = {
                "Completion %": st.column_config.ProgressColumn(
                    "Completion %",
                    min_value = 0,
                    max_value = 100,
                    format    = "%.0f%%",
                ),
            },
        )

    st.markdown("---")
    col3, col4 = st.columns(2)

    # ── Hidden gems ───────────────────────────────────────────────────────────
    with col3:
        st.subheader("Hidden gems")
        st.caption("Low play count (3–15) but ≥90% completion and ≤10% skip rate — songs saved for the right moment.")

        gems_display = d["hidden_gems"][[
            "track_name", "artist_name", "total_plays", "completion_pct", "skip_pct"
        ]].rename(columns={
            "track_name":     "Track",
            "artist_name":    "Artist",
            "total_plays":    "Plays",
            "completion_pct": "Completion %",
            "skip_pct":       "Skip %",
        })
        st.dataframe(
            gems_display,
            use_container_width = True,
            hide_index          = True,
            height              = 360,
        )

    # ── Skip vs completion scatter ─────────────────────────────────────────────
    with col4:
        st.subheader("Skip rate vs completion rate")
        st.caption("Each dot = one track (min 5 plays). Bottom-right = genuinely loved. Top-left = tolerated.")

        scatter_df = d["top_tracks"].copy()
        scatter_df = scatter_df[scatter_df["completion_pct"].notna()]

        fig7 = px.scatter(
            scatter_df,
            x         = "skip_pct",
            y         = "completion_pct",
            size      = "total_plays",
            hover_name = "track_name",
            hover_data = {"artist_name": True, "total_plays": True},
            color     = "hours_listened",
            color_continuous_scale = "Purples",
            labels    = {
                "skip_pct":       "Skip rate %",
                "completion_pct": "Completion rate %",
                "total_plays":    "Plays",
                "hours_listened": "Hours",
            },
        )
        fig7.update_layout(
            height = 360,
            margin = {"l": 0, "r": 0, "t": 10, "b": 0},
        )
        st.plotly_chart(fig7, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
# PAGE 4 — DE vs PK
# ═════════════════════════════════════════════════════════════════════════════
elif page == "DE vs PK":

    st.title("Germany vs Pakistan")
    st.caption("Same listener · two countries · two different listening lives")
    st.markdown("---")

    country_data = d["country"]
    summary_df   = country_data["summary"]
    de_row       = summary_df[summary_df["country"] == "DE"].iloc[0]
    pk_row       = summary_df[summary_df["country"] == "PK"].iloc[0]

    # ── Side-by-side KPIs ─────────────────────────────────────────────────────
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"### 🇩🇪 Germany (Berlin)")
        metric_row([
            ("Streams",        f"{de_row['total_streams']:,}",),
            ("Hours",          f"{de_row['total_hours']:,.0f} h",),
            ("Skip rate",      f"{de_row['skip_pct']}%",),
            ("Peak hour",      f"{int(de_row['peak_hour']):02d}:00",),
        ])

    with col2:
        st.markdown(f"### 🇵🇰 Pakistan (Karachi)")
        metric_row([
            ("Streams",        f"{pk_row['total_streams']:,}",),
            ("Hours",          f"{pk_row['total_hours']:,.0f} h",),
            ("Skip rate",      f"{pk_row['skip_pct']}%",),
            ("Peak hour",      f"{int(pk_row['peak_hour']):02d}:00",),
        ])

    st.markdown("---")
    col3, col4 = st.columns(2)

    # ── Top artists DE ─────────────────────────────────────────────────────────
    with col3:
        st.subheader("🇩🇪 Top artists in Germany")
        st.caption("Ranked by hours listened while connected in DE")

        de_artists = country_data["top_artists"][
            country_data["top_artists"]["country"] == "DE"
        ][["artist_name","hours_listened","streams","skip_pct"]]

        fig8 = px.bar(
            de_artists,
            x           = "hours_listened",
            y           = "artist_name",
            orientation = "h",
            color_discrete_sequence = [DE_COLOUR],
            labels      = {
                "hours_listened": "Hours",
                "artist_name":    "Artist",
            },
            hover_data  = ["streams", "skip_pct"],
        )
        fig8.update_layout(
            yaxis  = {"categoryorder": "total ascending"},
            height = 340,
            margin = {"l": 0, "r": 0, "t": 10, "b": 0},
            showlegend = False,
        )
        st.plotly_chart(fig8, use_container_width=True)

    # ── Top artists PK ─────────────────────────────────────────────────────────
    with col4:
        st.subheader("🇵🇰 Top artists in Pakistan")
        st.caption("Ranked by hours listened while connected in PK")

        pk_artists = country_data["top_artists"][
            country_data["top_artists"]["country"] == "PK"
        ][["artist_name","hours_listened","streams","skip_pct"]]

        fig9 = px.bar(
            pk_artists,
            x           = "hours_listened",
            y           = "artist_name",
            orientation = "h",
            color_discrete_sequence = [PK_COLOUR],
            labels      = {
                "hours_listened": "Hours",
                "artist_name":    "Artist",
            },
            hover_data  = ["streams", "skip_pct"],
        )
        fig9.update_layout(
            yaxis  = {"categoryorder": "total ascending"},
            height = 340,
            margin = {"l": 0, "r": 0, "t": 10, "b": 0},
            showlegend = False,
        )
        st.plotly_chart(fig9, use_container_width=True)

    # ── Peak hours comparison ──────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Peak listening hours")
    st.caption("Top 5 hours by stream count — when does each country version of you listen?")

    peak_df = country_data["peak_hours"]
    fig10 = px.bar(
        peak_df,
        x         = "hour",
        y         = "streams",
        color     = "country",
        barmode   = "group",
        color_discrete_map = COUNTRY_COLOURS,
        labels    = {
            "hour":    "Hour of day",
            "streams": "Streams",
            "country": "Country",
        },
    )
    fig10.update_layout(
        height = 300,
        margin = {"l": 0, "r": 0, "t": 10, "b": 0},
        xaxis  = {"dtick": 1},
    )
    st.plotly_chart(fig10, use_container_width=True)

    # ── Key differences callout ────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Key differences")

    c1, c2, c3 = st.columns(3)
    c1.info(
        f"**Skip rate gap**\n\n"
        f"DE: {de_row['skip_pct']}% vs PK: {pk_row['skip_pct']}%\n\n"
        f"You skipped {de_row['skip_pct'] - pk_row['skip_pct']:.1f}pp more in Germany"
    )
    c2.info(
        f"**Artist discovery**\n\n"
        f"DE: {int(de_row['unique_artists'])} artists · "
        f"PK: {int(pk_row['unique_artists'])} artists\n\n"
        f"{int(de_row['unique_artists'] - pk_row['unique_artists'])} more artists discovered in Germany"
    )
    c3.info(
        f"**Shuffle behaviour**\n\n"
        f"DE: {de_row['shuffle_pct']}% · PK: {pk_row['shuffle_pct']}%\n\n"
        f"More intentional listening in Germany"
    )


# ═════════════════════════════════════════════════════════════════════════════
# PAGE 5 — WEATHER
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Weather":

    st.title("Weather & listening")
    st.caption("Does the weather outside affect how much you listen? Historical data from Open-Meteo.")
    st.markdown("---")

    # ── Avg hours per day by season and country ────────────────────────────────
    st.subheader("Listening intensity by season")
    st.caption("Average hours per day grouped by season and country.")

    weather_df = d["weather"]
    season_summary = (
        weather_df
        .groupby(["country", "season"], as_index=False)
        .agg(
            avg_hours  = ("avg_hours_per_day", "mean"),
            avg_temp   = ("avg_temp_c",        "mean"),
            skip_pct   = ("skip_pct",          "mean"),
        )
        .round(2)
    )
    season_order = ["Winter", "Spring", "Summer", "Autumn"]

    fig11 = px.bar(
        season_summary,
        x         = "season",
        y         = "avg_hours",
        color     = "country",
        barmode   = "group",
        category_orders = {"season": season_order},
        color_discrete_map = COUNTRY_COLOURS,
        labels    = {
            "avg_hours": "Avg hours/day",
            "season":    "Season",
            "country":   "Country",
        },
        hover_data = ["avg_temp", "skip_pct"],
    )
    fig11.update_layout(
        height = 320,
        margin = {"l": 0, "r": 0, "t": 10, "b": 0},
    )
    st.plotly_chart(fig11, use_container_width=True)

    st.markdown("---")
    col1, col2 = st.columns(2)

    # ── Rainy vs dry ───────────────────────────────────────────────────────────
    with col1:
        st.subheader("Rainy vs dry days")
        st.caption("Does rain keep you on Spotify longer?")

        rainy_df = d["rainy_dry"]
        fig12 = px.bar(
            rainy_df,
            x         = "season",
            y         = "avg_hours_per_day",
            color     = "day_type",
            facet_col = "country",
            barmode   = "group",
            category_orders = {
                "season":   season_order,
                "day_type": ["Rainy", "Dry"],
            },
            color_discrete_map = {"Rainy": "#378ADD", "Dry": ACCENT},
            labels    = {
                "avg_hours_per_day": "Avg hours/day",
                "season":            "Season",
                "day_type":          "Day type",
            },
        )
        fig12.update_layout(
            height = 340,
            margin = {"l": 0, "r": 0, "t": 30, "b": 0},
        )
        st.plotly_chart(fig12, use_container_width=True)

    # ── Temperature vs hours scatter ───────────────────────────────────────────
    with col2:
        st.subheader("Temperature vs listening")
        st.caption("Each point = one weather/season/country group. Does heat or cold drive more listening?")

        fig13 = px.scatter(
            weather_df,
            x          = "avg_temp_c",
            y          = "avg_hours_per_day",
            color      = "country",
            symbol     = "season",
            size       = "avg_streams_per_day",
            hover_data = ["season", "temp_category", "skip_pct"],
            color_discrete_map = COUNTRY_COLOURS,
            labels     = {
                "avg_temp_c":        "Avg temperature (°C)",
                "avg_hours_per_day": "Avg hours/day",
                "country":           "Country",
                "season":            "Season",
            },
        )
        fig13.update_layout(
            height = 340,
            margin = {"l": 0, "r": 0, "t": 10, "b": 0},
        )
        st.plotly_chart(fig13, use_container_width=True)

    # ── Skip rate by weather ───────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Skip rate by temperature category")
    st.caption("Are you more patient with music when it's cold outside?")

    skip_weather = (
        weather_df
        .groupby(["country", "temp_category"], as_index=False)
        ["skip_pct"].mean().round(1)
    )
    temp_order = ["cold", "cool", "warm", "hot"]

    fig14 = px.bar(
        skip_weather,
        x         = "temp_category",
        y         = "skip_pct",
        color     = "country",
        barmode   = "group",
        category_orders = {"temp_category": temp_order},
        color_discrete_map = COUNTRY_COLOURS,
        labels    = {
            "skip_pct":      "Skip rate %",
            "temp_category": "Temperature",
            "country":       "Country",
        },
    )
    fig14.update_layout(
        height = 300,
        margin = {"l": 0, "r": 0, "t": 10, "b": 0},
    )
    st.plotly_chart(fig14, use_container_width=True)

    # ── Insight callouts ───────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Key findings")
    c1, c2, c3 = st.columns(3)

    c1.success(
        "**DE: Heat drives listening**\n\n"
        "Summer hot days (27°C+) averaged **3.92 hrs/day** — "
        "the highest of any weather group. Likely heatwave days spent indoors."
    )
    c2.success(
        "**PK: Rain drives listening**\n\n"
        "Rainy monsoon days in Pakistan averaged **1.21 hrs/day** "
        "vs 0.77 hrs on dry days — the opposite pattern to Germany."
    )
    c3.success(
        "**Weather < Country**\n\n"
        "Skip rate in PK (35–43%) stays consistently lower than DE (49–62%) "
        "across all weather conditions — the country effect dominates."
    )