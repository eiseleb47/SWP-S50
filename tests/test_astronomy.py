"""Tests for astronomy.py — moon emoji, night windows, and object visibility."""

from __future__ import annotations

import warnings
from datetime import date, datetime, timedelta

import numpy as np
import pytest
import pytz

from seestar.astronomy import AstronomyCalculator, _moon_phase_emoji, _effective_rating

TZ = pytz.timezone("Europe/Vienna")
VIENNA = {"lat": 48.2082, "lon": 16.3738}


# ─── _moon_phase_emoji ────────────────────────────────────────────────────────

class TestMoonPhaseEmoji:
    def test_new_moon(self):
        assert _moon_phase_emoji(0.01, 5.0) == "🌑"

    def test_full_moon(self):
        assert _moon_phase_emoji(0.99, 178.0) == "🌕"

    def test_waxing_crescent(self):
        emoji = _moon_phase_emoji(0.15, 45.0)
        assert emoji == "🌒"

    def test_waning_crescent(self):
        emoji = _moon_phase_emoji(0.15, 300.0)
        assert emoji == "🌘"

    def test_waxing_quarter(self):
        emoji = _moon_phase_emoji(0.40, 90.0)
        assert emoji == "🌓"

    def test_waning_quarter(self):
        emoji = _moon_phase_emoji(0.40, 270.0)
        assert emoji == "🌗"

    def test_returns_string_for_all_phases(self):
        """Every combination of illumination and phase should return a string."""
        for ill in np.linspace(0, 1, 11):
            for phase in np.linspace(0, 360, 13):
                result = _moon_phase_emoji(ill, phase)
                assert isinstance(result, str)
                assert len(result) > 0


# ─── _effective_rating ────────────────────────────────────────────────────────

class TestEffectiveRating:
    """Unit tests for the condition-adjusted rating helper."""

    def test_ideal_conditions_no_penalty(self):
        # Dark sky, no moon, well-sized object, long window → full rating
        assert _effective_rating(5, "broadband", 30, 0.0, 180, "Galaxy", 180) == 5

    def test_bright_moon_broadband_penalty_two(self):
        # > 85% illumination → −2 for broadband
        assert _effective_rating(5, "broadband", 30, 0.90, 90, "Galaxy", 180) == 3

    def test_medium_moon_broadband_penalty_one(self):
        # 60–85% illumination → −1 for broadband
        assert _effective_rating(5, "broadband", 30, 0.70, 90, "Galaxy", 180) == 4

    def test_bright_moon_narrowband_no_penalty(self):
        # Dual-band filter: 90% moon has no effect on narrowband
        assert _effective_rating(5, "narrowband", 30, 0.90, 90, "Emission Nebula", 180) == 5

    def test_very_bright_moon_narrowband_penalty(self):
        # > 95% → −1 even for narrowband
        assert _effective_rating(5, "narrowband", 30, 0.97, 90, "Emission Nebula", 180) == 4

    def test_close_moon_broadband_heavy_penalty(self):
        # Within ½ the separation threshold → −2
        # At 90% illum: threshold = 15 + 0.9*45 = 55.5°; half = 27.75°
        assert _effective_rating(5, "broadband", 30, 0.90, 20, "Galaxy", 180) == 1  # −2 moon illum −2 sep

    def test_close_moon_narrowband_penalty(self):
        # < 15° from moon with narrowband → −1
        assert _effective_rating(5, "narrowband", 30, 0.0, 10, "Emission Nebula", 180) == 4

    def test_size_too_small_penalty(self):
        # < 2 arcmin → −1
        assert _effective_rating(5, "narrowband", 1.5, 0.0, 180, "Planetary Nebula", 180) == 4

    def test_size_too_large_penalty(self):
        # > 150 arcmin → −1
        assert _effective_rating(5, "broadband", 200, 0.0, 180, "Galaxy", 180) == 4

    def test_short_window_nebula_heavy_penalty(self):
        # < 30 min, nebula/galaxy → −2
        assert _effective_rating(5, "narrowband", 30, 0.0, 180, "Emission Nebula", 15) == 3

    def test_medium_window_nebula_light_penalty(self):
        # 30–59 min, nebula → −1
        assert _effective_rating(5, "narrowband", 30, 0.0, 180, "Emission Nebula", 45) == 4

    def test_long_window_nebula_no_penalty(self):
        # ≥ 60 min → no duration penalty
        assert _effective_rating(5, "narrowband", 30, 0.0, 180, "Emission Nebula", 90) == 5

    def test_short_window_cluster_light_penalty(self):
        # < 15 min, cluster → −1 (lighter; clusters are bright)
        assert _effective_rating(5, "broadband", 20, 0.0, 180, "Globular Cluster", 10) == 4

    def test_15min_window_cluster_no_penalty(self):
        # 15 min is enough for a cluster
        assert _effective_rating(5, "broadband", 20, 0.0, 180, "Open Cluster", 15) == 5

    def test_default_window_no_penalty(self):
        # Default window_minutes=999 → no duration penalty
        assert _effective_rating(4, "broadband", 20, 0.0, 180, "Galaxy") == 4

    def test_floor_is_one(self):
        # Stacked penalties never drop below 1
        assert _effective_rating(1, "broadband", 0.5, 0.90, 5, "Galaxy", 10) == 1

    def test_stacked_penalties_clamped(self):
        # Many penalties on a low base rating → clamped to 1
        assert _effective_rating(2, "broadband", 200, 0.95, 10, "Galaxy", 10) == 1


# ─── AstronomyCalculator construction ────────────────────────────────────────

class TestAstronomyCalculatorInit:
    def test_instantiates_with_valid_params(self):
        calc = AstronomyCalculator(**VIENNA, timezone="Europe/Vienna")
        assert calc.lat == VIENNA["lat"]
        assert calc.lon == VIENNA["lon"]

    def test_default_elevation(self):
        calc = AstronomyCalculator(**VIENNA)
        assert calc.elevation == 200.0

    def test_timezone_attribute_set(self):
        calc = AstronomyCalculator(**VIENNA, timezone="Europe/Vienna")
        assert calc.timezone_str == "Europe/Vienna"

    def test_location_created(self):
        from astropy.coordinates import EarthLocation
        calc = AstronomyCalculator(**VIENNA)
        assert isinstance(calc.location, EarthLocation)


# ─── Fallback night window ────────────────────────────────────────────────────

class TestFallbackNightWindow:
    """The fallback is always available (no astroplan needed)."""

    def setup_method(self):
        self.calc = AstronomyCalculator(**VIENNA, timezone="Europe/Vienna")

    def test_returns_dict_with_all_keys(self):
        window = self.calc._fallback_night_window(date(2024, 6, 15))
        for key in ("sunset", "civil_evening", "nautical_evening", "astro_evening",
                    "astro_morning", "nautical_morning", "civil_morning", "sunrise"):
            assert key in window

    def test_evening_before_morning(self):
        window = self.calc._fallback_night_window(date(2024, 6, 15))
        assert window["astro_evening"] < window["astro_morning"]

    def test_sunset_before_astro_evening(self):
        window = self.calc._fallback_night_window(date(2024, 6, 15))
        assert window["sunset"] < window["astro_evening"]

    def test_astro_morning_before_sunrise(self):
        window = self.calc._fallback_night_window(date(2024, 6, 15))
        assert window["astro_morning"] < window["sunrise"]

    def test_all_values_are_timezone_aware(self):
        window = self.calc._fallback_night_window(date(2024, 6, 15))
        for key, val in window.items():
            assert val.tzinfo is not None, f"{key} is not timezone-aware"


# ─── get_night_window (real astroplan or fallback) ────────────────────────────

class TestGetNightWindow:
    def setup_method(self):
        self.calc = AstronomyCalculator(**VIENNA, timezone="Europe/Vienna")

    def test_returns_expected_keys(self):
        window = self.calc.get_night_window(date(2024, 6, 15))
        for key in ("sunset", "astro_evening", "astro_morning", "sunrise"):
            assert key in window

    def test_astro_evening_before_astro_morning(self):
        window = self.calc.get_night_window(date(2024, 6, 15))
        eve = window.get("astro_evening")
        mor = window.get("astro_morning")
        if eve and mor:
            assert eve < mor

    def test_window_is_in_local_timezone(self):
        window = self.calc.get_night_window(date(2024, 6, 15))
        for key, val in window.items():
            if val is not None:
                # Should be expressible in local tz (tzinfo present)
                assert val.tzinfo is not None, f"{key} has no tzinfo"

    def test_different_seasons_give_different_windows(self):
        """Astronomical night is longer in winter than summer at mid-latitudes."""
        summer = self.calc.get_night_window(date(2024, 6, 21))
        winter = self.calc.get_night_window(date(2024, 12, 21))

        s_eve = summer.get("astro_evening")
        s_mor = summer.get("astro_morning")
        w_eve = winter.get("astro_evening")
        w_mor = winter.get("astro_morning")

        if all(t is not None for t in (s_eve, s_mor, w_eve, w_mor)):
            summer_len = (s_mor - s_eve).total_seconds()
            winter_len = (w_mor - w_eve).total_seconds()
            assert winter_len > summer_len


# ─── get_object_altitudes ─────────────────────────────────────────────────────

class TestGetObjectAltitudes:
    def setup_method(self):
        self.calc = AstronomyCalculator(**VIENNA, timezone="Europe/Vienna")

    def test_returns_array_same_length_as_times(self):
        import pandas as pd
        from astropy.coordinates import SkyCoord

        coord = SkyCoord(ra="05h35m17s", dec="-05d23m28s", frame="icrs")
        times = pd.date_range("2024-01-15 20:00", periods=8, freq="1h", tz="UTC")
        alts  = self.calc.get_object_altitudes(coord, times)
        assert len(alts) == 8

    def test_altitudes_are_degrees(self):
        import pandas as pd
        from astropy.coordinates import SkyCoord

        coord = SkyCoord(ra="05h35m17s", dec="-05d23m28s", frame="icrs")
        times = pd.date_range("2024-01-15 22:00", periods=4, freq="1h", tz="UTC")
        alts  = self.calc.get_object_altitudes(coord, times)
        # All altitudes must be within [-90, 90]
        assert np.all(alts >= -90)
        assert np.all(alts <= 90)


# ─── get_visible_objects_tonight ─────────────────────────────────────────────

class TestGetVisibleObjectsTonight:
    def setup_method(self):
        self.calc = AstronomyCalculator(**VIENNA, timezone="Europe/Vienna")

    def _night_window(self, month: int = 6) -> dict:
        base = TZ.localize(datetime(2024, month, 15, 22, 0))
        return {
            "astro_evening": base,
            "astro_morning": base + timedelta(hours=7),
        }

    def test_returns_list(self):
        result = self.calc.get_visible_objects_tonight(self._night_window())
        assert isinstance(result, list)

    def test_all_returned_objects_have_max_altitude(self):
        result = self.calc.get_visible_objects_tonight(self._night_window(), min_altitude=25.0)
        for obj in result:
            assert "max_altitude" in obj
            assert obj["max_altitude"] >= 25.0

    def test_results_sorted_by_effective_rating_desc(self):
        result = self.calc.get_visible_objects_tonight(self._night_window())
        ratings = [o["effective_rating"] for o in result]
        # Check monotonically non-increasing (ties OK)
        for i in range(len(ratings) - 1):
            assert ratings[i] >= ratings[i + 1]

    def test_empty_window_returns_empty_list(self):
        window = {"astro_evening": None, "astro_morning": None}
        result = self.calc.get_visible_objects_tonight(window)
        assert result == []

    def test_high_min_altitude_reduces_count(self):
        low  = self.calc.get_visible_objects_tonight(self._night_window(), min_altitude=10)
        high = self.calc.get_visible_objects_tonight(self._night_window(), min_altitude=60)
        assert len(low) >= len(high)

    def test_visible_objects_have_window_start_end(self):
        result = self.calc.get_visible_objects_tonight(self._night_window())
        for obj in result:
            assert "window_start" in obj
            assert "window_end"   in obj

    def test_visible_objects_have_effective_rating(self):
        result = self.calc.get_visible_objects_tonight(self._night_window())
        for obj in result:
            assert "effective_rating" in obj
            assert 1 <= obj["effective_rating"] <= 5

    def test_moon_interference_flag_present(self):
        moon_info = {
            "illumination": 0.8,
            "phase_emoji": "🌕",
            "rise": None, "set": None,
            "altitude": 45.0, "azimuth": 180.0,
        }
        result = self.calc.get_visible_objects_tonight(
            self._night_window(), moon_info=moon_info
        )
        for obj in result:
            assert "moon_interference" in obj
