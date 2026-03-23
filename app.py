"""
Seestar S50 Observation Planner — Streamlit app entry point.
"""

from __future__ import annotations

import warnings
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytz
import streamlit as st

# Page config must be the very first Streamlit call
st.set_page_config(
    page_title="Seestar S50 — Observation Planner",
    page_icon="🔭",
    layout="wide",
    initial_sidebar_state="expanded",
)

from seestar.weather import get_weather_data
from seestar.astronomy import AstronomyCalculator
from seestar.analysis import (
    calculate_hourly_scores,
    get_best_nights,
    get_night_scores,
    summarize_tonight,
    score_label_color,
)
from seestar.charts import create_meteogram, create_observing_window_chart, dso_card_html
from seestar.catalog import get_skycoord

# ─── Known locations ──────────────────────────────────────────────────────────

LOCATIONS: dict[str, dict | None] = {
    "Vienna":          {"lat": 48.2082, "lon": 16.3738, "timezone": "Europe/Vienna"},
    "Klosterneuburg":  {"lat": 48.3058, "lon": 16.3253, "timezone": "Europe/Vienna"},
    "St. Pölten":      {"lat": 48.2047, "lon": 15.6256, "timezone": "Europe/Vienna"},
    "Wiener Neustadt": {"lat": 47.8130, "lon": 16.2458, "timezone": "Europe/Vienna"},
    "Krems":           {"lat": 48.4092, "lon": 15.6139, "timezone": "Europe/Vienna"},
    "Custom":          None,
}


# ─── Cached weather fetch ─────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def _load_weather(lat: float, lon: float):
    return get_weather_data(lat, lon)


# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🔭 Seestar S50")
    st.markdown("**Observation Planner**")
    st.divider()

    location_name = st.selectbox("Location", list(LOCATIONS.keys()), index=0)

    if location_name == "Custom":
        lat = st.number_input(
            "Latitude (°N)", value=48.2082,
            min_value=-90.0, max_value=90.0, step=0.0001, format="%.4f",
        )
        lon = st.number_input(
            "Longitude (°E)", value=16.3738,
            min_value=-180.0, max_value=180.0, step=0.0001, format="%.4f",
        )
        tz_str = st.text_input("Timezone (IANA)", value="Europe/Vienna")
    else:
        loc    = LOCATIONS[location_name]
        lat    = loc["lat"]
        lon    = loc["lon"]
        tz_str = loc["timezone"]

    st.divider()
    min_altitude = st.slider("Min. object altitude (°)", 15, 45, 25, step=5,
                             help="Objects below this elevation are excluded.")
    show_planets = st.checkbox("Include planets", value=True)

    st.divider()
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    with st.expander("ℹ️ About ZWO Seestar S50"):
        st.markdown(
            """
**ZWO Seestar S50** is a compact smart telescope for astrophotography.

| Spec | Value |
|------|-------|
| Aperture | 50 mm |
| Focal length | 250 mm (f/5) |
| Sensor | Sony IMX462C |
| Filter | Dual-band (Hα + OIII) |
| FOV | ~1.5° × 1.1° |
| Mount | Alt-Az + auto-tracking |

The built-in dual-band narrowband filter lets you capture emission
nebulae even from light-polluted city skies.
            """
        )


# ─── Initialise timezone and load data ────────────────────────────────────────

try:
    tz = pytz.timezone(tz_str)
except Exception:
    tz = pytz.timezone("Europe/Vienna")
    st.warning(f"Unknown timezone '{tz_str}', falling back to Europe/Vienna.")

with st.spinner("Fetching 7-day weather forecast…"):
    try:
        df, seventimer_ok = _load_weather(lat, lon)
    except Exception as exc:
        st.error(f"Failed to fetch weather data: {exc}")
        st.stop()

if not seventimer_ok:
    st.warning(
        "⚠️ 7timer seeing/transparency data unavailable. "
        "Scores are based on cloud cover only."
    )


# ─── Astronomical calculations ────────────────────────────────────────────────

astro = AstronomyCalculator(lat=lat, lon=lon, timezone=tz_str)
now   = datetime.now(tz)

# If it's before noon, tonight is really last night → look back one day
obs_date = (now - timedelta(days=1)).date() if now.hour < 12 else now.date()

with st.spinner("Calculating astronomical events…"):
    night_window = astro.get_night_window(obs_date)
    moon_info    = astro.get_moon_info(now)

    # Night windows for all 7 forecast days (for meteogram shading)
    night_windows_all = [astro.get_night_window(obs_date + timedelta(days=i)) for i in range(7)]

    visible_objects = astro.get_visible_objects_tonight(
        night_window=night_window,
        min_altitude=min_altitude,
        moon_info=moon_info,
    )
    planets = astro.get_planet_visibility(night_window) if show_planets else []

# Attach altitude curves to the first 6 DSO objects for the window chart
night_df = get_night_scores(df, night_window, tz)
if not night_df.empty:
    from astropy.time import Time
    from astropy.coordinates import AltAz

    times_utc_idx = night_df.index.tz_convert("UTC")
    times_local_list = night_df.index.to_pydatetime()
    ap_times = Time(times_utc_idx.to_pydatetime())
    aa_frame = AltAz(obstime=ap_times, location=astro.location)

    for obj in visible_objects[:6]:
        try:
            coord = get_skycoord(obj)
            alts  = coord.transform_to(aa_frame).alt.deg
            obj["altitudes"]  = alts.tolist()
            obj["alt_times"]  = times_local_list
        except Exception:
            pass

summary     = summarize_tonight(night_df, night_window, moon_info, seventimer_ok)
best_nights = get_best_nights(df, tz)


# ─── Page header ──────────────────────────────────────────────────────────────

st.title("🔭 Seestar S50 Observation Planner")
st.caption(
    f"📍 {location_name}  ·  {lat:.4f}°N, {lon:.4f}°E  ·  "
    f"{now.strftime('%A, %d %B %Y  %H:%M %Z')}"
)


# ─── Tonight's top metrics ────────────────────────────────────────────────────

c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    st.metric(
        "Tonight's Score",
        f"{summary['overall_score']:.0f} / 100",
        delta=summary["overall_label"],
    )
with c2:
    # Average cloud cover during the astronomical night
    if not night_df.empty:
        cloud_avg = night_df["cloud_cover"].mean()
        cloud_str = f"{cloud_avg:.0f}%" if not np.isnan(cloud_avg) else "—"
    else:
        cloud_str = "—"
    st.metric("Avg Cloud Cover", cloud_str)
with c3:
    st.metric(
        "Moon",
        f"{moon_info['phase_emoji']} {int(moon_info['illumination'] * 100)}%",
    )
with c4:
    st.metric("Best Hour", summary.get("best_hour", "—"))
with c5:
    st.metric("Objects Tonight", len(visible_objects) + len(planets))


# Colour-coded summary box
box_color = summary["overall_color"]
st.markdown(
    f"""<div style="
        background: rgba(0,0,0,0.28);
        border-left: 4px solid {box_color};
        padding: 12px 18px;
        border-radius: 6px;
        margin: 10px 0 4px 0;
        line-height: 1.65;
    ">{summary["summary_text"]}</div>""",
    unsafe_allow_html=True,
)

st.divider()


# ─── 7-day meteogram ──────────────────────────────────────────────────────────

st.subheader("7-Day Weather Forecast")
fig_meteo = create_meteogram(df, tz, night_windows=night_windows_all, title="")
st.plotly_chart(fig_meteo, use_container_width=True)


# ─── Nightly score cards ──────────────────────────────────────────────────────

if not best_nights.empty:
    st.subheader("Nightly Overview")
    n_cols = min(len(best_nights), 7)
    night_cols = st.columns(n_cols)
    for i, (_, row) in enumerate(best_nights.head(7).iterrows()):
        col   = night_cols[i]
        color = row["color"]
        nd    = row["night_date"]
        day   = datetime(nd.year, nd.month, nd.day).strftime("%a")
        date_str = nd.strftime("%d %b")
        with col:
            st.markdown(
                f"""<div style="
                    text-align: center;
                    background: rgba(0,0,0,0.30);
                    border: 1px solid {color};
                    border-radius: 10px;
                    padding: 10px 6px;
                ">
                <div style="font-weight:bold; font-size:1.0em;">{day}</div>
                <div style="font-size:0.78em; color:#aaa;">{date_str}</div>
                <div style="font-size:1.5em; font-weight:bold; color:{color}; line-height:1.2;">{row['avg_score']:.0f}</div>
                <div style="font-size:0.72em; color:{color};">{row['label']}</div>
                <div style="font-size:0.68em; color:#888;">{row['clear_hours']}h ≥ Good</div>
                </div>""",
                unsafe_allow_html=True,
            )

st.divider()


# ─── Tonight's observing window ───────────────────────────────────────────────

st.subheader("Tonight's Observing Window")
fig_window = create_observing_window_chart(
    night_df=night_df,
    night_window=night_window,
    visible_objects=visible_objects,
    moon_info=moon_info,
    tz=tz,
)
st.plotly_chart(fig_window, use_container_width=True)


# Twilight table + moon info side by side
tw_left, tw_right = st.columns(2)

def _fmt(dt) -> str:
    return dt.strftime("%H:%M") if dt else "—"

with tw_left:
    st.markdown("**Evening twilight**")
    st.dataframe(
        pd.DataFrame({
            "Event": ["Sunset", "Civil", "Nautical", "Astronomical Dark"],
            "Time":  [
                _fmt(night_window.get("sunset")),
                _fmt(night_window.get("civil_evening")),
                _fmt(night_window.get("nautical_evening")),
                _fmt(night_window.get("astro_evening")),
            ],
        }),
        hide_index=True, use_container_width=True,
    )

with tw_right:
    st.markdown("**Morning twilight**")
    st.dataframe(
        pd.DataFrame({
            "Event": ["Astronomical Dawn", "Nautical", "Civil", "Sunrise"],
            "Time":  [
                _fmt(night_window.get("astro_morning")),
                _fmt(night_window.get("nautical_morning")),
                _fmt(night_window.get("civil_morning")),
                _fmt(night_window.get("sunrise")),
            ],
        }),
        hide_index=True, use_container_width=True,
    )

# Moon info
mc1, mc2, mc3, mc4 = st.columns(4)
mc1.metric("Moon Phase",    moon_info["phase_emoji"])
mc2.metric("Illumination",  f"{int(moon_info['illumination']*100)}%")
mc3.metric("Moonrise",      _fmt(moon_info.get("rise")))
mc4.metric("Moonset",       _fmt(moon_info.get("set")))

st.divider()


# ─── Object recommendations ───────────────────────────────────────────────────

total_targets = len(visible_objects) + len(planets)
st.subheader(f"Recommended Objects Tonight  ({total_targets} above {min_altitude}°)")

# Planets row
if planets:
    st.markdown("**Solar System**")
    planet_cols = st.columns(min(len(planets), 4))
    for i, p in enumerate(planets):
        with planet_cols[i % 4]:
            rating = "★" * p["seestar_rating"] + "☆" * (5 - p["seestar_rating"])
            st.markdown(
                f"""<div style="
                    background: rgba(0,0,0,0.38);
                    border: 1px solid #444;
                    border-radius: 8px;
                    padding: 12px;
                    margin: 4px 0;
                ">
                <div style="font-size:1.05em; font-weight:bold;">🪐 {p['name']}</div>
                <div style="font-size:0.78em; color:#aaa;">Planet</div>
                <div style="color:#FFD700; font-size:0.88em;">{rating}</div>
                <div style="font-size:0.78em; color:#ccc; margin-top:5px;">
                    Max alt: {p['max_altitude']:.0f}°
                </div>
                <div style="font-size:0.70em; color:#9ab; margin-top:5px; font-style:italic;">{p['notes']}</div>
                </div>""",
                unsafe_allow_html=True,
            )

if visible_objects:
    st.markdown("**Deep Sky Objects**")

    # Controls: filter by type
    types_available = sorted({o["type"] for o in visible_objects})
    filter_type = st.multiselect(
        "Filter by type",
        options=types_available,
        default=types_available,
        label_visibility="collapsed",
    )
    filtered = [o for o in visible_objects if o["type"] in filter_type]

    for row_start in range(0, min(len(filtered), 15), 3):
        row_objs = filtered[row_start: row_start + 3]
        cols = st.columns(3)
        for col, obj in zip(cols, row_objs):
            with col:
                st.markdown(dso_card_html(obj), unsafe_allow_html=True)

elif not planets:
    st.info(
        f"No objects found above {min_altitude}° during tonight's astronomical night. "
        "Try lowering the minimum altitude threshold in the sidebar."
    )

st.divider()
st.caption(
    "Weather: [Open-Meteo](https://open-meteo.com) (ECMWF/ICON/GFS) + "
    "[7timer ASTRO](http://7timer.info) seeing/transparency.  "
    "Astronomical calculations: [astroplan](https://astroplan.readthedocs.io) + "
    "[astropy](https://www.astropy.org).  "
    "Tailored for the [ZWO Seestar S50](https://www.zwoastro.com/product/seestar-s50)."
)
