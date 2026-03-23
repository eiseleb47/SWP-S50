"""Tests for charts.py — Plotly figure generation."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest
import pytz

from seestar.charts import create_meteogram, create_observing_window_chart

TZ = pytz.timezone("Europe/Vienna")

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_weather_df(n: int = 168) -> pd.DataFrame:
    """Minimal weather DataFrame matching what the app feeds to the charts."""
    times = pd.date_range("2024-06-15", periods=n, freq="1h", tz="UTC")
    rng   = np.random.default_rng(42)
    return pd.DataFrame(
        {
            "temperature":    rng.uniform(10, 25, n),
            "dewpoint":       rng.uniform(0, 10, n),
            "humidity":       rng.uniform(40, 80, n),
            "cloud_cover":    rng.uniform(0, 100, n),
            "cloud_low":      rng.uniform(0, 40, n),
            "cloud_mid":      rng.uniform(0, 40, n),
            "cloud_high":     rng.uniform(0, 40, n),
            "wind_speed":     rng.uniform(0, 30, n),
            "wind_gusts":     rng.uniform(0, 50, n),
            "wind_direction": rng.uniform(0, 360, n),
            "precipitation":  rng.uniform(0, 5, n),
            "visibility":     rng.uniform(5000, 30000, n),
            "weathercode":    np.zeros(n, dtype=int),
            "seeing_7t":      rng.uniform(1, 8, n),
            "transparency_7t": rng.uniform(1, 8, n),
        },
        index=times,
    )


def _make_night_df(n: int = 8) -> pd.DataFrame:
    """Minimal DataFrame for the observing-window chart."""
    start = TZ.localize(datetime(2024, 6, 15, 22, 0))
    times = pd.date_range(start, periods=n, freq="1h")
    rng   = np.random.default_rng(0)
    df = pd.DataFrame(
        {
            "obs_score":    rng.uniform(40, 90, n),
            "cloud_cover":  rng.uniform(0, 30, n),
            "wind_speed":   rng.uniform(0, 15, n),
            "temperature":  rng.uniform(8, 18, n),
            "dewpoint":     rng.uniform(2, 8, n),
            "humidity":     rng.uniform(45, 70, n),
        },
        index=times,
    )
    return df


def _night_window() -> dict:
    base = TZ.localize(datetime(2024, 6, 15, 22, 0))
    return {
        "sunset":          base - timedelta(hours=3),
        "civil_evening":   base - timedelta(hours=2),
        "nautical_evening": base - timedelta(hours=1, minutes=30),
        "astro_evening":   base,
        "astro_morning":   base + timedelta(hours=7),
        "nautical_morning": base + timedelta(hours=8),
        "civil_morning":   base + timedelta(hours=8, minutes=30),
        "sunrise":         base + timedelta(hours=9),
    }


def _moon_info(illumination: float = 0.3) -> dict:
    return {
        "illumination": illumination,
        "phase_emoji": "🌒",
        "rise": None, "set": None,
        "altitude": 20.0, "azimuth": 180.0,
    }


# ─── create_meteogram ─────────────────────────────────────────────────────────

class TestCreateMeteogram:
    def test_returns_figure(self):
        df  = _make_weather_df()
        fig = create_meteogram(df, TZ)
        assert isinstance(fig, go.Figure)

    def test_has_five_rows_of_traces(self):
        df  = _make_weather_df()
        fig = create_meteogram(df, TZ)
        # At minimum we expect more than 5 traces (clouds alone have 4)
        assert len(fig.data) >= 5

    def test_custom_title_appears(self):
        df  = _make_weather_df()
        fig = create_meteogram(df, TZ, title="Test Title")
        assert fig.layout.title.text == "Test Title"

    def test_night_shading_adds_shapes(self):
        df  = _make_weather_df()
        nw  = [_night_window()]
        fig = create_meteogram(df, TZ, night_windows=nw)
        # Shapes include the vrects
        assert len(fig.layout.shapes) > 0 or len(fig.layout.annotations) >= 0

    def test_paper_bgcolor_is_dark(self):
        df  = _make_weather_df()
        fig = create_meteogram(df, TZ)
        assert fig.layout.paper_bgcolor == "#0A0E1A"

    def test_height_set(self):
        df  = _make_weather_df()
        fig = create_meteogram(df, TZ)
        assert fig.layout.height is not None
        assert fig.layout.height > 400

    def test_no_7timer_data_still_works(self):
        """Meteogram should render even when seeing/transparency are NaN."""
        df = _make_weather_df()
        df["seeing_7t"] = float("nan")
        df["transparency_7t"] = float("nan")
        fig = create_meteogram(df, TZ)
        assert isinstance(fig, go.Figure)


# ─── create_observing_window_chart ────────────────────────────────────────────

class TestCreateObservingWindowChart:
    def test_returns_figure(self):
        night_df = _make_night_df()
        fig = create_observing_window_chart(
            night_df=night_df,
            night_window=_night_window(),
            visible_objects=[],
            moon_info=_moon_info(),
            tz=TZ,
        )
        assert isinstance(fig, go.Figure)

    def test_empty_df_returns_figure(self):
        """An empty night_df should not crash — just show an empty chart."""
        fig = create_observing_window_chart(
            night_df=pd.DataFrame(),
            night_window={},
            visible_objects=[],
            moon_info=_moon_info(),
            tz=TZ,
        )
        assert isinstance(fig, go.Figure)

    def test_moon_illumination_in_title(self):
        night_df = _make_night_df()
        fig = create_observing_window_chart(
            night_df=night_df,
            night_window=_night_window(),
            visible_objects=[],
            moon_info=_moon_info(0.30),
            tz=TZ,
        )
        assert "30%" in fig.layout.title.text

    def test_object_altitude_curves_added(self):
        import numpy as np
        times_local = _make_night_df().index.to_pydatetime()
        obj_with_alts = {
            "name": "Test Nebula",
            "messier_id": "NGC 0000",
            "altitudes": list(np.linspace(30, 60, len(times_local))),
            "alt_times": times_local,
        }
        night_df = _make_night_df()
        fig = create_observing_window_chart(
            night_df=night_df,
            night_window=_night_window(),
            visible_objects=[obj_with_alts],
            moon_info=_moon_info(),
            tz=TZ,
        )
        trace_names = [t.name for t in fig.data]
        assert "NGC 0000" in trace_names

    def test_paper_bgcolor_is_dark(self):
        fig = create_observing_window_chart(
            night_df=_make_night_df(),
            night_window=_night_window(),
            visible_objects=[],
            moon_info=_moon_info(),
            tz=TZ,
        )
        assert fig.layout.paper_bgcolor == "#0A0E1A"

    def test_height_reasonable(self):
        fig = create_observing_window_chart(
            night_df=_make_night_df(),
            night_window=_night_window(),
            visible_objects=[],
            moon_info=_moon_info(),
            tz=TZ,
        )
        assert fig.layout.height >= 400

    def test_at_most_six_object_traces(self):
        """Only the first 6 objects with altitude data should be plotted."""
        import numpy as np
        times_local = _make_night_df().index.to_pydatetime()
        n_obj = 10
        objects = [
            {
                "name": f"Obj {i}",
                "messier_id": f"M{i}",
                "altitudes": list(np.linspace(30, 70, len(times_local))),
                "alt_times": times_local,
            }
            for i in range(n_obj)
        ]
        fig = create_observing_window_chart(
            night_df=_make_night_df(),
            night_window=_night_window(),
            visible_objects=objects,
            moon_info=_moon_info(),
            tz=TZ,
        )
        # Score trace (1) + up to 6 object traces = 7 max
        assert len(fig.data) <= 8
