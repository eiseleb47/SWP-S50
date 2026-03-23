"""
Observing quality analysis for the Seestar S50 Observation Planner.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import pytz


# ─── Score categories ─────────────────────────────────────────────────────────

SCORE_TIERS = [
    (80, "Excellent", "#00CC44"),
    (60, "Good",      "#88CC00"),
    (40, "Fair",      "#FFEE00"),
    (20, "Poor",      "#FF8800"),
    (0,  "Bad",       "#FF3333"),
]


def score_label_color(score: float) -> tuple[str, str]:
    """Return (label, hex_color) for the given 0-100 score."""
    for threshold, label, color in SCORE_TIERS:
        if score >= threshold:
            return label, color
    return "Bad", "#FF3333"


# ─── Per-hour score ───────────────────────────────────────────────────────────

def _coerce(row: pd.Series, key: str, default: float) -> float:
    """Return float value of row[key], or default if absent/NaN."""
    v = row.get(key)
    return float(v) if v is not None and pd.notna(v) else float(default)


def _row_score(row: pd.Series) -> float:
    """Calculate observing score (0-100) for a single hourly row."""
    cloud_cover  = _coerce(row, "cloud_cover",  50)
    seeing       = row.get("seeing_7t")
    transparency = row.get("transparency_7t")
    wind_speed   = _coerce(row, "wind_speed",   10)
    temp         = _coerce(row, "temperature",  10)
    dewpoint     = _coerce(row, "dewpoint",      5)
    humidity     = _coerce(row, "humidity",     70)

    cloud_factor = 1.0 - cloud_cover / 100.0

    if pd.notna(seeing) and seeing:
        seeing_factor = (9.0 - float(seeing)) / 8.0
    else:
        # Proxy: clear sky → assume better seeing
        seeing_factor = 0.40 + cloud_factor * 0.30

    if pd.notna(transparency) and transparency:
        transparency_factor = (9.0 - float(transparency)) / 8.0
    else:
        transparency_factor = 0.40 + cloud_factor * 0.30

    wind_factor = max(0.0, 1.0 - wind_speed / 50.0)

    dew_margin = temp - dewpoint
    dew_factor = min(1.0, max(0.0, dew_margin / 10.0))

    humidity_factor = max(0.0, 1.0 - max(0.0, humidity - 60.0) / 60.0)

    inner = (
        seeing_factor       * 0.35
        + transparency_factor * 0.25
        + wind_factor         * 0.20
        + dew_factor          * 0.10
        + humidity_factor     * 0.10
    )
    return round(max(0.0, min(100.0, cloud_factor * inner * 100.0)), 1)


def calculate_hourly_scores(df: pd.DataFrame) -> pd.Series:
    """Return a Series of per-hour observing scores (0-100)."""
    return pd.Series(
        [_row_score(row) for _, row in df.iterrows()],
        index=df.index,
        name="obs_score",
    )


# ─── Nightly summary ──────────────────────────────────────────────────────────

def get_best_nights(df: pd.DataFrame, tz: pytz.BaseTzInfo) -> pd.DataFrame:
    """
    One-row-per-night summary DataFrame with columns:
    night_date, avg_score, max_score, clear_hours, label, color.
    "Night" hours = 20:00–08:00 local.
    """
    df_local = df.copy()
    df_local.index = df_local.index.tz_convert(tz)
    scores = calculate_hourly_scores(df_local)

    nights: dict[date, list[float]] = {}
    for ts, score in scores.items():
        h = ts.hour
        if h >= 20:
            night_date = ts.date()
        elif h < 8:
            night_date = (ts - pd.Timedelta(days=1)).date()
        else:
            continue
        nights.setdefault(night_date, []).append(score)

    rows = []
    for night_date, night_scores in sorted(nights.items()):
        avg = float(np.mean(night_scores))
        mx  = float(np.max(night_scores))
        clear = int(sum(1 for s in night_scores if s >= 60))
        label, color = score_label_color(avg)
        rows.append(
            {
                "night_date":  night_date,
                "avg_score":   round(avg, 1),
                "max_score":   round(mx, 1),
                "clear_hours": clear,
                "label":       label,
                "color":       color,
            }
        )
    return pd.DataFrame(rows)


def get_night_scores(
    df: pd.DataFrame,
    night_window: dict,
    tz: pytz.BaseTzInfo,
) -> pd.DataFrame:
    """
    Return the rows of df that fall inside the astronomical night window,
    with an added 'obs_score' column.
    """
    t_start = night_window.get("astro_evening")
    t_end   = night_window.get("astro_morning")
    if t_start is None or t_end is None:
        return pd.DataFrame()

    df_local = df.copy()
    df_local.index = df_local.index.tz_convert(tz)

    mask = (df_local.index >= t_start) & (df_local.index <= t_end)
    night_df = df_local.loc[mask].copy()
    if night_df.empty:
        return night_df

    night_df["obs_score"] = calculate_hourly_scores(night_df).values
    return night_df


# ─── Text summary ─────────────────────────────────────────────────────────────

def summarize_tonight(
    night_scores_df: pd.DataFrame,
    night_window: dict,
    moon_info: dict,
    seventimer_ok: bool,
) -> dict:
    """Return a summary dict for display in the app header."""
    if night_scores_df.empty:
        return {
            "overall_label": "No Data",
            "overall_color": "#888888",
            "overall_score": 0.0,
            "max_score":     0.0,
            "best_hour":     "—",
            "clear_hours":   0,
            "summary_text":  "No forecast data available for tonight.",
        }

    scores = night_scores_df["obs_score"]
    avg_score = float(scores.mean())
    max_score = float(scores.max())
    label, color = score_label_color(avg_score)
    clear_hours = int((scores >= 60).sum())
    best_ts = scores.idxmax()
    best_hour = best_ts.strftime("%H:%M") if hasattr(best_ts, "strftime") else "—"

    moon_pct   = int(moon_info.get("illumination", 0) * 100)
    moon_emoji = moon_info.get("phase_emoji", "🌑")

    lines = []

    if avg_score >= 60:
        lines.append(
            f"Conditions look <strong>{label.lower()}</strong> for your Seestar S50 tonight."
        )
    elif avg_score >= 40:
        lines.append(
            "Conditions are <strong>marginal</strong> tonight. Observing may be possible during clearer periods."
        )
    else:
        lines.append(
            "Tonight's conditions are <strong>not favorable</strong> for observing."
        )

    if clear_hours > 0:
        lines.append(
            f"~{clear_hours} hour(s) with score ≥ 60 (Good or better). "
            f"Best hour around <strong>{best_hour}</strong>."
        )

    moon_line = f"{moon_emoji} Moon is <strong>{moon_pct}%</strong> illuminated. "
    if moon_pct < 25:
        moon_line += "Ideal for dark-sky targets (galaxies, faint nebulae)."
    elif moon_pct < 60:
        moon_line += "Emission nebulae with the dual-band filter are still excellent."
    else:
        moon_line += "Favour narrowband targets (emission nebulae) or bright clusters."
    lines.append(moon_line)

    astro_eve = night_window.get("astro_evening")
    astro_mor = night_window.get("astro_morning")
    if astro_eve and astro_mor:
        lines.append(
            f"Astronomical dark: <strong>{astro_eve.strftime('%H:%M')}</strong> – "
            f"<strong>{astro_mor.strftime('%H:%M')}</strong> local time."
        )

    if not seventimer_ok:
        lines.append(
            "⚠️ 7timer seeing/transparency data unavailable; scores derived from cloud cover only."
        )

    return {
        "overall_label": label,
        "overall_color": color,
        "overall_score": round(avg_score, 1),
        "max_score":     round(max_score, 1),
        "best_hour":     best_hour,
        "clear_hours":   clear_hours,
        "summary_text":  "  \n".join(lines),
    }
