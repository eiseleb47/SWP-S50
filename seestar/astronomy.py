"""
Astronomical calculations for the Seestar S50 Observation Planner.
Uses astroplan and astropy for twilight, moon, and object visibility.
"""

from __future__ import annotations

import math
import warnings
from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import pytz

from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body
from astropy.time import Time
import astropy.units as u

try:
    from astroplan import Observer
    ASTROPLAN_OK = True
except ImportError:
    ASTROPLAN_OK = False
    warnings.warn("astroplan not available; using fallback calculations")

from .catalog import DSO_CATALOG, get_skycoord


class AstronomyCalculator:
    def __init__(
        self,
        lat: float,
        lon: float,
        elevation: float = 200.0,
        timezone: str = "Europe/Vienna",
    ):
        self.lat = lat
        self.lon = lon
        self.elevation = elevation
        self.timezone_str = timezone
        self.tz = pytz.timezone(timezone)
        self.location = EarthLocation(
            lat=lat * u.deg,
            lon=lon * u.deg,
            height=elevation * u.m,
        )
        if ASTROPLAN_OK:
            self.observer = Observer(
                location=self.location,
                timezone=timezone,
            )
        else:
            self.observer = None

    def get_night_window(self, for_date: date) -> dict:
        """
        Get the astronomical night window for the night that starts on for_date.
        Uses local noon as the reference point and looks for the *next* events.
        Returns a dict of timezone-aware local datetimes.
        """
        if not ASTROPLAN_OK:
            return self._fallback_night_window(for_date)

        noon_local = self.tz.localize(
            datetime(for_date.year, for_date.month, for_date.day, 12, 0, 0)
        )
        t_noon = Time(noon_local)

        result = {}
        pairs = [
            ("sunset", self.observer.sun_set_time),
            ("civil_evening", self.observer.twilight_evening_civil),
            ("nautical_evening", self.observer.twilight_evening_nautical),
            ("astro_evening", self.observer.twilight_evening_astronomical),
            ("astro_morning", self.observer.twilight_morning_astronomical),
            ("nautical_morning", self.observer.twilight_morning_nautical),
            ("civil_morning", self.observer.twilight_morning_civil),
            ("sunrise", self.observer.sun_rise_time),
        ]
        for key, method in pairs:
            try:
                t = method(t_noon, which="next")
                result[key] = t.to_datetime(timezone=self.tz)
            except Exception:
                result[key] = None

        return result

    def get_moon_info(self, dt: datetime) -> dict:
        """Return moon data at the given (timezone-aware) local datetime."""
        if not ASTROPLAN_OK:
            return self._fallback_moon_info()

        if dt.tzinfo is None:
            dt = self.tz.localize(dt)
        t = Time(dt)

        try:
            illumination = float(self.observer.moon_illumination(t))
        except Exception:
            illumination = 0.0

        try:
            moonrise = self.observer.moon_rise_time(t, which="nearest")
            moonrise_local = moonrise.to_datetime(timezone=self.tz)
        except Exception:
            moonrise_local = None

        try:
            moonset = self.observer.moon_set_time(t, which="nearest")
            moonset_local = moonset.to_datetime(timezone=self.tz)
        except Exception:
            moonset_local = None

        try:
            phase_rad = float(self.observer.moon_phase(t).value)
        except Exception:
            phase_rad = math.pi / 2

        try:
            altaz = self.observer.moon_altaz(t)
            moon_alt = float(altaz.alt.deg)
            moon_az = float(altaz.az.deg)
        except Exception:
            moon_alt = 0.0
            moon_az = 0.0

        phase_deg = math.degrees(phase_rad)
        return {
            "illumination": illumination,
            "phase_angle_deg": phase_deg,
            "phase_emoji": _moon_phase_emoji(illumination, phase_deg),
            "rise": moonrise_local,
            "set": moonset_local,
            "altitude": moon_alt,
            "azimuth": moon_az,
        }

    def get_object_altitudes(
        self,
        coord: SkyCoord,
        times_utc: pd.DatetimeIndex,
    ) -> np.ndarray:
        """Return altitude (degrees) of coord at each UTC time."""
        ap_times = Time(times_utc.to_pydatetime())
        frame = AltAz(obstime=ap_times, location=self.location)
        return coord.transform_to(frame).alt.deg

    def get_visible_objects_tonight(
        self,
        night_window: dict,
        min_altitude: float = 25.0,
        moon_info: Optional[dict] = None,
    ) -> list:
        """
        Return catalog objects visible tonight (altitude >= min_altitude during
        astronomical night), sorted by seestar_rating DESC, max_altitude DESC.
        Each dict is augmented with max_altitude, window_start/end, moon_separation,
        moon_interference.
        """
        t_start = night_window.get("astro_evening")
        t_end = night_window.get("astro_morning")
        if t_start is None or t_end is None:
            return []

        n_hours = max(2, int((t_end - t_start).total_seconds() / 3600) + 1)
        times_local = pd.date_range(t_start, periods=n_hours, freq="1h")
        times_utc = times_local.tz_convert("UTC")

        moon_illum = moon_info.get("illumination", 0.0) if moon_info else 0.0

        visible = []
        for obj in DSO_CATALOG:
            try:
                coord = get_skycoord(obj)
                alts = self.get_object_altitudes(coord, times_utc)
                max_alt = float(np.max(alts))
                if max_alt < min_altitude:
                    continue

                above = alts >= min_altitude
                if not np.any(above):
                    continue

                first_i = int(np.argmax(above))
                last_i = int(len(above) - 1 - np.argmax(above[::-1]))

                # Moon angular separation at peak altitude
                peak_i = int(np.argmax(alts))
                moon_sep = 180.0
                moon_interference = False
                if moon_info is not None and moon_illum > 0.15:
                    try:
                        moon_coord = get_body(
                            "moon",
                            Time(times_utc[peak_i].to_pydatetime()),
                            self.location,
                        )
                        moon_sep = float(coord.separation(moon_coord.icrs).deg)
                        threshold = 15 if obj["filter_type"] == "narrowband" else 30
                        moon_interference = moon_sep < threshold
                    except Exception:
                        pass

                aug = dict(obj)
                aug["max_altitude"] = round(max_alt, 1)
                aug["window_start"] = times_local[first_i]
                aug["window_end"] = times_local[last_i]
                aug["moon_separation"] = round(moon_sep, 1)
                aug["moon_interference"] = moon_interference
                visible.append(aug)
            except Exception:
                continue

        visible.sort(key=lambda o: (-o["seestar_rating"], -o["max_altitude"]))
        return visible

    def get_planet_visibility(self, night_window: dict) -> list:
        """Return planets above 15° tonight with their max altitude."""
        t_start = night_window.get("astro_evening")
        t_end = night_window.get("astro_morning")
        if t_start is None:
            return []
        if t_end is None:
            t_end = t_start + timedelta(hours=6)

        n_hours = max(2, int((t_end - t_start).total_seconds() / 3600) + 1)
        times_local = pd.date_range(t_start, periods=n_hours, freq="1h")
        times_utc = times_local.tz_convert("UTC")
        ap_times = Time(times_utc.to_pydatetime())

        planets_list = [
            ("Venus", "venus", 5),
            ("Mars", "mars", 4),
            ("Jupiter", "jupiter", 5),
            ("Saturn", "saturn", 5),
            ("Uranus", "uranus", 3),
            ("Neptune", "neptune", 2),
        ]
        visible = []
        for display_name, body_name, rating in planets_list:
            try:
                coords = get_body(body_name, ap_times, self.location)
                frame = AltAz(obstime=ap_times, location=self.location)
                alts = coords.transform_to(frame).alt.deg
                max_alt = float(np.max(alts))
                if max_alt >= 15:
                    visible.append(
                        {
                            "name": display_name,
                            "type": "Planet",
                            "max_altitude": round(max_alt, 1),
                            "filter_type": "broadband",
                            "seestar_rating": rating,
                            "notes": f"Solar system planet. Max altitude tonight: {max_alt:.0f}°.",
                        }
                    )
            except Exception:
                continue

        visible.sort(key=lambda p: -p["max_altitude"])
        return visible

    # ── Fallbacks ─────────────────────────────────────────────────────────────

    def _fallback_night_window(self, for_date: date) -> dict:
        tz = self.tz
        base = datetime(for_date.year, for_date.month, for_date.day)
        return {
            "sunset":          tz.localize(base.replace(hour=18, minute=30)),
            "civil_evening":   tz.localize(base.replace(hour=19, minute=0)),
            "nautical_evening": tz.localize(base.replace(hour=19, minute=45)),
            "astro_evening":   tz.localize(base.replace(hour=20, minute=30)),
            "astro_morning":   tz.localize(base.replace(hour=4, minute=30) + timedelta(days=1)),
            "nautical_morning": tz.localize(base.replace(hour=5, minute=15) + timedelta(days=1)),
            "civil_morning":   tz.localize(base.replace(hour=6, minute=0) + timedelta(days=1)),
            "sunrise":         tz.localize(base.replace(hour=6, minute=30) + timedelta(days=1)),
        }

    def _fallback_moon_info(self) -> dict:
        return {
            "illumination": 0.5,
            "phase_angle_deg": 90.0,
            "phase_emoji": "🌓",
            "rise": None,
            "set": None,
            "altitude": 0.0,
            "azimuth": 0.0,
        }


def _moon_phase_emoji(illumination: float, phase_angle_deg: float) -> str:
    """Map illumination + phase angle to a moon-phase emoji."""
    ill = illumination
    waxing = phase_angle_deg <= 180
    if ill < 0.03:
        return "🌑"
    elif ill < 0.25:
        return "🌒" if waxing else "🌘"
    elif ill < 0.50:
        return "🌓" if waxing else "🌗"
    elif ill < 0.75:
        return "🌔" if waxing else "🌖"
    elif ill < 0.97:
        return "🌔" if waxing else "🌖"
    else:
        return "🌕"
