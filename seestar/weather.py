"""
Weather data integration for Seestar S50 Observation Planner.
Fetches from Open-Meteo (hourly) and 7timer ASTRO (3-hourly), merges both.
"""

from __future__ import annotations

import warnings
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
import requests

# ─── API endpoints ────────────────────────────────────────────────────────────
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
SEVENTIMER_URL = "https://www.7timer.info/bin/api.pl"

# 7timer cloud cover midpoints (scale 1-9)
_7T_CLOUD_MIDPOINTS = {1: 3, 2: 12, 3: 25, 4: 37, 5: 50, 6: 62, 7: 75, 8: 87, 9: 97}

# 7timer wind speed midpoints km/h (scale 1-8)
_7T_WIND_KMH = {1: 0, 2: 3, 3: 11, 4: 20, 5: 35, 6: 60, 7: 80, 8: 117}


def _cloud_from_7t(code: int) -> float:
    """Convert 7timer cloud cover code (1-9) to percentage (0-100)."""
    return float(_7T_CLOUD_MIDPOINTS.get(int(code), 50))


def _wind_from_7t(code: int) -> float:
    """Convert 7timer wind speed code (1-8) to km/h."""
    return float(_7T_WIND_KMH.get(int(code), 20))


# ─── Open-Meteo ───────────────────────────────────────────────────────────────

def fetch_open_meteo(lat: float, lon: float) -> pd.DataFrame:
    """
    Fetch 7-day hourly forecast from Open-Meteo.

    Returns a DataFrame indexed by UTC datetime with columns:
        temperature, dewpoint, humidity, cloud_cover, cloud_low, cloud_mid,
        cloud_high, wind_speed, wind_gusts, wind_direction, precipitation,
        visibility, weathercode
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join([
            "temperature_2m",
            "dewpoint_2m",
            "relativehumidity_2m",
            "cloudcover",
            "cloudcover_low",
            "cloudcover_mid",
            "cloudcover_high",
            "windspeed_10m",
            "windgusts_10m",
            "winddirection_10m",
            "precipitation",
            "visibility",
            "weathercode",
        ]),
        "models": "best_match",
        "forecast_days": 7,
        "timezone": "UTC",
    }

    resp = requests.get(OPEN_METEO_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    hourly = data["hourly"]
    times = pd.to_datetime(hourly["time"], utc=True)

    df = pd.DataFrame(
        {
            "temperature": hourly["temperature_2m"],
            "dewpoint": hourly["dewpoint_2m"],
            "humidity": hourly["relativehumidity_2m"],
            "cloud_cover": hourly["cloudcover"],
            "cloud_low": hourly["cloudcover_low"],
            "cloud_mid": hourly["cloudcover_mid"],
            "cloud_high": hourly["cloudcover_high"],
            "wind_speed": hourly["windspeed_10m"],
            "wind_gusts": hourly["windgusts_10m"],
            "wind_direction": hourly["winddirection_10m"],
            "precipitation": hourly["precipitation"],
            "visibility": hourly["visibility"],
            "weathercode": hourly["weathercode"],
        },
        index=times,
    )
    df.index.name = "time"
    return df


# ─── 7timer ASTRO ─────────────────────────────────────────────────────────────

def fetch_7timer(lat: float, lon: float) -> Optional[pd.DataFrame]:
    """
    Fetch ASTRO product from 7timer.info.

    Returns a DataFrame with 3-hourly UTC datetimes and columns:
        seeing_7t (1-8), transparency_7t (1-8), lifted_index,
        cloud_cover_7t (%), wind_speed_7t (km/h)
    Returns None on failure.
    """
    params = {
        "lon": lon,
        "lat": lat,
        "product": "astro",
        "output": "json",
    }
    try:
        resp = requests.get(SEVENTIMER_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout as exc:
        warnings.warn(f"7timer timed out: {exc}")
        return None
    except requests.exceptions.ConnectionError as exc:
        warnings.warn(f"7timer connection error: {exc}")
        return None
    except requests.exceptions.HTTPError as exc:
        warnings.warn(f"7timer HTTP error: {exc}")
        return None
    except ValueError as exc:
        warnings.warn(f"7timer returned invalid JSON: {exc}")
        return None

    try:
        init_str = str(data["init"])  # e.g. "2024030918"
        init_dt = datetime(
            int(init_str[0:4]),
            int(init_str[4:6]),
            int(init_str[6:8]),
            int(init_str[8:10]),
            tzinfo=timezone.utc,
        )

        rows = []
        for tp in data["dataseries"]:
            offset_h = int(tp["timepoint"]) * 3  # timepoints in 3h steps? no – it's the index
            # Actually 7timer uses "timepoint" as hours from init
            dt = init_dt + pd.Timedelta(hours=int(tp["timepoint"]))
            rows.append(
                {
                    "time": dt,
                    "seeing_7t": int(tp.get("seeing", 0)) or None,
                    "transparency_7t": int(tp.get("transparency", 0)) or None,
                    "lifted_index": tp.get("lifted_index"),
                    "cloud_cover_7t": _cloud_from_7t(tp.get("cloudcover", 5)),
                    "wind_speed_7t": _wind_from_7t(
                        tp.get("wind10m", {}).get("speed", 1)
                        if isinstance(tp.get("wind10m"), dict)
                        else 1
                    ),
                }
            )

        df = pd.DataFrame(rows).set_index("time")
        df.index = pd.DatetimeIndex(df.index, tz=timezone.utc)
        return df

    except Exception as exc:
        warnings.warn(f"7timer parse error: {exc}")
        return None


# ─── Merge ────────────────────────────────────────────────────────────────────

def merge_weather(
    om_df: pd.DataFrame,
    st_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """
    Merge Open-Meteo hourly data with optional 7timer 3-hourly data.

    7timer columns are interpolated to hourly and joined to Open-Meteo.
    If st_df is None, seeing/transparency are filled with NaN.
    """
    merged = om_df.copy()

    if st_df is not None and not st_df.empty:
        # Reindex 7timer to the Open-Meteo hourly grid, interpolate
        st_reindexed = st_df.reindex(
            st_df.index.union(merged.index)
        ).sort_index()

        # Interpolate numeric columns (seeing/transparency are ordinal – nearest is fine for them)
        for col in ["cloud_cover_7t", "wind_speed_7t", "lifted_index"]:
            if col in st_reindexed.columns:
                st_reindexed[col] = (
                    st_reindexed[col].astype(float).interpolate(method="time")
                )
        for col in ["seeing_7t", "transparency_7t"]:
            if col in st_reindexed.columns:
                st_reindexed[col] = (
                    st_reindexed[col].astype(float).ffill().bfill()
                )

        st_hourly = st_reindexed.reindex(merged.index)
        for col in st_hourly.columns:
            merged[col] = st_hourly[col].values
    else:
        merged["seeing_7t"] = np.nan
        merged["transparency_7t"] = np.nan
        merged["cloud_cover_7t"] = np.nan
        merged["wind_speed_7t"] = np.nan
        merged["lifted_index"] = np.nan

    return merged


# ─── Public convenience ───────────────────────────────────────────────────────

def get_weather_data(lat: float, lon: float) -> tuple[pd.DataFrame, bool]:
    """
    Fetch and merge weather data for the given location.

    Returns
    -------
    df : pd.DataFrame
        Merged hourly weather DataFrame (UTC index).
    seventimer_ok : bool
        True if 7timer data was successfully retrieved.
    """
    om_df = fetch_open_meteo(lat, lon)
    st_df = fetch_7timer(lat, lon)
    merged = merge_weather(om_df, st_df)
    return merged, st_df is not None
