"""Tests for weather.py — API parsers, converters and merge logic."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from seestar.weather import (
    _cloud_from_7t,
    _wind_from_7t,
    fetch_open_meteo,
    fetch_7timer,
    merge_weather,
    get_weather_data,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────

N_HOURS = 168  # 7 days × 24 h


def _make_om_response(n: int = N_HOURS) -> dict:
    """Minimal but structurally correct Open-Meteo JSON response."""
    times = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return {
        "hourly": {
            "time":                [t.strftime("%Y-%m-%dT%H:%M") for t in times],
            "temperature_2m":      [10.0] * n,
            "dewpoint_2m":         [5.0]  * n,
            "relativehumidity_2m": [60.0] * n,
            "cloudcover":          [20.0] * n,
            "cloudcover_low":      [5.0]  * n,
            "cloudcover_mid":      [8.0]  * n,
            "cloudcover_high":     [12.0] * n,
            "windspeed_10m":       [8.0]  * n,
            "windgusts_10m":       [12.0] * n,
            "winddirection_10m":   [270.0] * n,
            "precipitation":       [0.0]  * n,
            "visibility":          [20000.0] * n,
            "weathercode":         [0]    * n,
        }
    }


def _make_7timer_response(n_points: int = 16) -> dict:
    """Minimal but structurally correct 7timer ASTRO JSON response."""
    dataseries = []
    for i in range(n_points):
        dataseries.append({
            "timepoint":    i * 3 + 3,
            "cloudcover":   2,
            "seeing":       3,
            "transparency": 4,
            "lifted_index": 6,
            "rh2m":         11,
            "wind10m":      {"direction": "W", "speed": 2},
            "temp2m":       18,
            "prec_type":    "none",
        })
    return {"product": "astro", "init": "2024010112", "dataseries": dataseries}


# ─── Unit conversion ──────────────────────────────────────────────────────────

class TestCloudFrom7t:
    def test_code_1_is_clear(self):
        assert _cloud_from_7t(1) == 3       # 0-6% → midpoint 3

    def test_code_5_is_half(self):
        assert _cloud_from_7t(5) == 50      # 44-56% → midpoint 50

    def test_code_9_is_overcast(self):
        assert _cloud_from_7t(9) == 97      # 94-100% → midpoint 97

    def test_unknown_code_returns_fallback(self):
        result = _cloud_from_7t(99)
        assert result == 50                 # dict.get default


class TestWindFrom7t:
    def test_code_1_is_calm(self):
        assert _wind_from_7t(1) == 0

    def test_code_3_is_light_breeze(self):
        assert _wind_from_7t(3) == 11

    def test_unknown_code_returns_fallback(self):
        result = _wind_from_7t(99)
        assert result == 20


# ─── fetch_open_meteo ─────────────────────────────────────────────────────────

class TestFetchOpenMeteo:
    def test_returns_dataframe_with_expected_columns(self):
        expected_cols = {
            "temperature", "dewpoint", "humidity",
            "cloud_cover", "cloud_low", "cloud_mid", "cloud_high",
            "wind_speed", "wind_gusts", "wind_direction",
            "precipitation", "visibility", "weathercode",
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_om_response()
        mock_resp.raise_for_status = MagicMock()

        with patch("seestar.weather.requests.get", return_value=mock_resp):
            df = fetch_open_meteo(48.21, 16.37)

        assert isinstance(df, pd.DataFrame)
        assert expected_cols.issubset(set(df.columns))

    def test_returns_168_rows_for_7_days(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_om_response(N_HOURS)
        mock_resp.raise_for_status = MagicMock()

        with patch("seestar.weather.requests.get", return_value=mock_resp):
            df = fetch_open_meteo(48.21, 16.37)

        assert len(df) == N_HOURS

    def test_index_is_utc(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_om_response()
        mock_resp.raise_for_status = MagicMock()

        with patch("seestar.weather.requests.get", return_value=mock_resp):
            df = fetch_open_meteo(48.21, 16.37)

        assert df.index.tz is not None
        assert str(df.index.tz) == "UTC"

    def test_raises_on_http_error(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("HTTP 500")

        with patch("seestar.weather.requests.get", return_value=mock_resp):
            with pytest.raises(Exception):
                fetch_open_meteo(48.21, 16.37)


# ─── fetch_7timer ─────────────────────────────────────────────────────────────

class TestFetch7timer:
    def test_returns_dataframe_on_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_7timer_response()
        mock_resp.raise_for_status = MagicMock()

        with patch("seestar.weather.requests.get", return_value=mock_resp):
            df = fetch_7timer(48.21, 16.37)

        assert isinstance(df, pd.DataFrame)
        assert "seeing_7t" in df.columns
        assert "transparency_7t" in df.columns
        assert "cloud_cover_7t" in df.columns

    def test_returns_none_on_network_error(self):
        with patch("seestar.weather.requests.get", side_effect=Exception("timeout")):
            result = fetch_7timer(48.21, 16.37)

        assert result is None

    def test_returns_none_on_bad_json(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"product": "astro", "init": "BAD", "dataseries": []}
        mock_resp.raise_for_status = MagicMock()

        with patch("seestar.weather.requests.get", return_value=mock_resp):
            result = fetch_7timer(48.21, 16.37)

        # Bad init string → parse error → returns None
        assert result is None

    def test_cloud_cover_converted_from_code(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_7timer_response()
        mock_resp.raise_for_status = MagicMock()

        with patch("seestar.weather.requests.get", return_value=mock_resp):
            df = fetch_7timer(48.21, 16.37)

        assert not df.empty
        # Code 2 → 12%
        assert df["cloud_cover_7t"].iloc[0] == pytest.approx(12.0)


# ─── merge_weather ────────────────────────────────────────────────────────────

class TestMergeWeather:
    def _make_om_df(self) -> pd.DataFrame:
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_om_response()
        mock_resp.raise_for_status = MagicMock()
        with patch("seestar.weather.requests.get", return_value=mock_resp):
            return fetch_open_meteo(48.21, 16.37)

    def _make_7t_df(self) -> pd.DataFrame:
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_7timer_response()
        mock_resp.raise_for_status = MagicMock()
        with patch("seestar.weather.requests.get", return_value=mock_resp):
            return fetch_7timer(48.21, 16.37)

    def test_merge_with_7timer_adds_seeing_column(self):
        om_df = self._make_om_df()
        st_df = self._make_7t_df()
        merged = merge_weather(om_df, st_df)
        assert "seeing_7t" in merged.columns

    def test_merge_without_7timer_fills_nan(self):
        om_df = self._make_om_df()
        merged = merge_weather(om_df, None)
        assert "seeing_7t" in merged.columns
        assert merged["seeing_7t"].isna().all()

    def test_merged_length_matches_open_meteo(self):
        om_df = self._make_om_df()
        st_df = self._make_7t_df()
        merged = merge_weather(om_df, st_df)
        assert len(merged) == len(om_df)

    def test_open_meteo_columns_preserved(self):
        om_df = self._make_om_df()
        merged = merge_weather(om_df, None)
        assert "temperature" in merged.columns
        assert "cloud_cover" in merged.columns


# ─── get_weather_data (integration smoke test with mocks) ─────────────────────

class TestGetWeatherData:
    def test_returns_tuple_of_df_and_bool(self):
        om_mock = MagicMock()
        om_mock.json.return_value = _make_om_response()
        om_mock.raise_for_status = MagicMock()

        st_mock = MagicMock()
        st_mock.json.return_value = _make_7timer_response()
        st_mock.raise_for_status = MagicMock()

        call_count = [0]

        def side_effect(url, **kwargs):
            call_count[0] += 1
            return om_mock if "open-meteo" in url else st_mock

        with patch("seestar.weather.requests.get", side_effect=side_effect):
            df, ok = get_weather_data(48.21, 16.37)

        assert isinstance(df, pd.DataFrame)
        assert isinstance(ok, bool)
