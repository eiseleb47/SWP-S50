"""Tests for analysis.py — observing score and nightly summary logic."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
import pytz

from analysis import (
    _row_score,
    calculate_hourly_scores,
    get_best_nights,
    get_night_scores,
    score_label_color,
    summarize_tonight,
)

TZ = pytz.timezone("Europe/Vienna")


# ─── score_label_color ────────────────────────────────────────────────────────

class TestScoreLabelColor:
    @pytest.mark.parametrize("score,expected_label", [
        (100,  "Excellent"),
        (80,   "Excellent"),
        (79.9, "Good"),
        (60,   "Good"),
        (59.9, "Fair"),
        (40,   "Fair"),
        (39.9, "Poor"),
        (20,   "Poor"),
        (19.9, "Bad"),
        (0,    "Bad"),
    ])
    def test_label(self, score, expected_label):
        label, _ = score_label_color(score)
        assert label == expected_label

    def test_color_is_hex_string(self):
        for score in [0, 25, 50, 75, 100]:
            _, color = score_label_color(score)
            assert color.startswith("#")
            assert len(color) == 7


# ─── _row_score ───────────────────────────────────────────────────────────────

class TestRowScore:
    def _perfect(self) -> pd.Series:
        return pd.Series({
            "cloud_cover":    0.0,
            "seeing_7t":      1.0,    # best seeing
            "transparency_7t": 1.0,  # best transparency
            "wind_speed":     0.0,
            "temperature":   15.0,
            "dewpoint":       5.0,   # 10°C dew margin
            "humidity":      30.0,
        })

    def _overcast(self) -> pd.Series:
        row = self._perfect()
        row["cloud_cover"] = 100.0
        return row

    def test_perfect_conditions_near_100(self):
        assert _row_score(self._perfect()) >= 95.0

    def test_overcast_is_zero(self):
        assert _row_score(self._overcast()) == pytest.approx(0.0)

    def test_50pct_cloud_reduces_score_significantly(self):
        row = self._perfect()
        row["cloud_cover"] = 50.0
        score = _row_score(row)
        assert score < 55.0   # half the cloud factor halves the result

    def test_high_wind_reduces_score(self):
        row = self._perfect()
        row["wind_speed"] = 45.0
        score_windy = _row_score(row)
        score_calm  = _row_score(self._perfect())
        assert score_windy < score_calm

    def test_dew_risk_reduces_score(self):
        row = self._perfect()
        row["temperature"] = 10.0
        row["dewpoint"]    = 9.5   # only 0.5°C margin
        score_dew  = _row_score(row)
        score_norm = _row_score(self._perfect())
        assert score_dew < score_norm

    def test_poor_seeing_reduces_score(self):
        row = self._perfect()
        row["seeing_7t"] = 8.0   # worst seeing
        score_bad  = _row_score(row)
        score_good = _row_score(self._perfect())
        assert score_bad < score_good

    def test_none_seeing_uses_proxy(self):
        row = self._perfect()
        row["seeing_7t"] = None
        # Should not raise and should return a reasonable value
        score = _row_score(row)
        assert 0.0 <= score <= 100.0

    def test_missing_columns_use_defaults(self):
        row = pd.Series({"cloud_cover": 10.0})
        score = _row_score(row)
        assert 0.0 <= score <= 100.0

    def test_score_bounded_0_to_100(self):
        for cloud in np.linspace(0, 100, 11):
            row = self._perfect()
            row["cloud_cover"] = cloud
            score = _row_score(row)
            assert 0.0 <= score <= 100.0


# ─── calculate_hourly_scores ──────────────────────────────────────────────────

def _make_df(n: int = 48) -> pd.DataFrame:
    times = pd.date_range("2024-06-15 00:00", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "cloud_cover":    [10.0] * n,
            "cloud_low":      [2.0]  * n,
            "cloud_mid":      [4.0]  * n,
            "cloud_high":     [6.0]  * n,
            "seeing_7t":      [2.0]  * n,
            "transparency_7t": [2.0] * n,
            "wind_speed":     [5.0]  * n,
            "wind_gusts":     [8.0]  * n,
            "temperature":    [12.0] * n,
            "dewpoint":       [4.0]  * n,
            "humidity":       [55.0] * n,
            "precipitation":  [0.0]  * n,
            "weathercode":    [0]    * n,
        },
        index=times,
    )


class TestCalculateHourlyScores:
    def test_returns_series_same_length(self):
        df = _make_df(48)
        scores = calculate_hourly_scores(df)
        assert isinstance(scores, pd.Series)
        assert len(scores) == 48

    def test_scores_bounded(self):
        df = _make_df()
        scores = calculate_hourly_scores(df)
        assert (scores >= 0).all()
        assert (scores <= 100).all()

    def test_clear_night_scores_well(self):
        df = _make_df()
        scores = calculate_hourly_scores(df)
        assert scores.mean() >= 60.0

    def test_overcast_scores_zero(self):
        df = _make_df()
        df["cloud_cover"] = 100.0
        scores = calculate_hourly_scores(df)
        assert (scores == 0.0).all()

    def test_index_matches_input(self):
        df = _make_df(24)
        scores = calculate_hourly_scores(df)
        assert scores.index.equals(df.index)


# ─── get_best_nights ──────────────────────────────────────────────────────────

class TestGetBestNights:
    def test_returns_dataframe(self):
        df = _make_df(168)
        result = get_best_nights(df, TZ)
        assert isinstance(result, pd.DataFrame)

    def test_has_expected_columns(self):
        df = _make_df(168)
        result = get_best_nights(df, TZ)
        for col in ("night_date", "avg_score", "max_score", "clear_hours", "label", "color"):
            assert col in result.columns

    def test_scores_bounded(self):
        df = _make_df(168)
        result = get_best_nights(df, TZ)
        assert (result["avg_score"] >= 0).all()
        assert (result["avg_score"] <= 100).all()


# ─── get_night_scores ─────────────────────────────────────────────────────────

class TestGetNightScores:
    def _window(self):
        base = TZ.localize(datetime(2024, 6, 15, 22, 0))
        return {
            "astro_evening": base,
            "astro_morning": base + timedelta(hours=7),
        }

    def test_returns_dataframe_within_window(self):
        df = _make_df(168)
        result = get_night_scores(df, self._window(), TZ)
        assert isinstance(result, pd.DataFrame)
        assert "obs_score" in result.columns

    def test_empty_when_no_window(self):
        df = _make_df(48)
        result = get_night_scores(df, {"astro_evening": None, "astro_morning": None}, TZ)
        assert result.empty

    def test_row_count_within_window(self):
        df = _make_df(168)
        result = get_night_scores(df, self._window(), TZ)
        # 7 hours of window → up to 8 rows
        assert 1 <= len(result) <= 9


# ─── summarize_tonight ────────────────────────────────────────────────────────

class TestSummarizeTonight:
    def _moon(self, illumination: float = 0.3) -> dict:
        return {
            "illumination": illumination,
            "phase_emoji": "🌒",
            "rise": None, "set": None,
            "altitude": 20.0, "azimuth": 180.0,
        }

    def _window(self) -> dict:
        base = TZ.localize(datetime(2024, 6, 15, 22, 0))
        return {
            "astro_evening": base,
            "astro_morning": base + timedelta(hours=7),
        }

    def test_empty_df_returns_no_data(self):
        result = summarize_tonight(pd.DataFrame(), {}, self._moon(), True)
        assert result["overall_score"] == 0.0
        assert "No" in result["summary_text"]

    def test_good_night_returns_positive_label(self):
        df = _make_df(7)
        times = pd.date_range(
            TZ.localize(datetime(2024, 6, 15, 22, 0)),
            periods=7, freq="1h",
        )
        df_night = df.copy()
        df_night.index = times
        df_night["obs_score"] = [80.0] * 7
        result = summarize_tonight(df_night, self._window(), self._moon(), True)
        assert result["overall_label"] in ("Excellent", "Good")
        assert result["overall_score"] >= 60.0

    def test_returns_all_expected_keys(self):
        df_night = pd.DataFrame(
            {"obs_score": [75.0] * 5},
            index=pd.date_range(
                TZ.localize(datetime(2024, 6, 15, 22, 0)),
                periods=5, freq="1h",
            ),
        )
        result = summarize_tonight(df_night, self._window(), self._moon(), True)
        for key in ("overall_label", "overall_color", "overall_score", "max_score",
                    "best_hour", "clear_hours", "summary_text"):
            assert key in result

    def test_seventimer_warning_in_text_when_unavailable(self):
        df_night = pd.DataFrame(
            {"obs_score": [40.0] * 4},
            index=pd.date_range(
                TZ.localize(datetime(2024, 6, 15, 22, 0)),
                periods=4, freq="1h",
            ),
        )
        result = summarize_tonight(df_night, self._window(), self._moon(), seventimer_ok=False)
        assert "7timer" in result["summary_text"] or "seeing" in result["summary_text"].lower()
