"""Tests for catalog.py — DSO catalog integrity and helper functions."""

import pytest
from astropy.coordinates import SkyCoord

from seestar.catalog import (
    DSO_CATALOG,
    TYPE_ICON,
    get_objects_by_filter,
    get_objects_by_type,
    get_objects_for_month,
    get_skycoord,
    rating_stars,
    type_icon,
)

REQUIRED_KEYS = {
    "name",
    "messier_id",
    "ra",
    "dec",
    "type",
    "magnitude",
    "size_arcmin",
    "constellation",
    "best_months",
    "seestar_rating",
    "filter_type",
    "notes",
}


class TestCatalogIntegrity:
    def test_catalog_not_empty(self):
        assert len(DSO_CATALOG) >= 30

    def test_all_entries_have_required_keys(self):
        for obj in DSO_CATALOG:
            missing = REQUIRED_KEYS - set(obj.keys())
            assert not missing, f"'{obj['name']}' is missing keys: {missing}"

    def test_seestar_rating_in_valid_range(self):
        for obj in DSO_CATALOG:
            assert 1 <= obj["seestar_rating"] <= 5, (
                f"'{obj['name']}' has invalid seestar_rating {obj['seestar_rating']}"
            )

    def test_filter_type_is_valid(self):
        valid = {"narrowband", "broadband", "visual"}
        for obj in DSO_CATALOG:
            assert obj["filter_type"] in valid, (
                f"'{obj['name']}' has invalid filter_type '{obj['filter_type']}'"
            )

    def test_best_months_are_valid_month_numbers(self):
        for obj in DSO_CATALOG:
            for m in obj["best_months"]:
                assert 1 <= m <= 12, (
                    f"'{obj['name']}' has invalid month {m}"
                )

    def test_magnitude_is_numeric(self):
        for obj in DSO_CATALOG:
            assert isinstance(obj["magnitude"], (int, float))

    def test_ra_dec_are_parseable(self):
        """Every RA/Dec string must be parseable by astropy."""
        for obj in DSO_CATALOG:
            try:
                SkyCoord(ra=obj["ra"], dec=obj["dec"], frame="icrs")
            except Exception as exc:
                pytest.fail(f"'{obj['name']}' RA/Dec parse failed: {exc}")

    def test_no_duplicate_names(self):
        names = [o["name"] for o in DSO_CATALOG]
        assert len(names) == len(set(names)), "Duplicate object names found"


class TestGetSkycoord:
    def test_returns_skycoord(self):
        coord = get_skycoord(DSO_CATALOG[0])
        assert isinstance(coord, SkyCoord)

    def test_orion_nebula_ra_dec(self):
        orion = next(o for o in DSO_CATALOG if o["messier_id"] == "M42")
        coord = get_skycoord(orion)
        assert abs(coord.ra.deg - 83.82) < 0.1
        assert abs(coord.dec.deg - (-5.39)) < 0.1


class TestFilterHelpers:
    def test_get_objects_by_type_emission_nebula(self):
        results = get_objects_by_type("Emission Nebula")
        assert len(results) > 0
        for obj in results:
            assert "emission nebula" in obj["type"].lower()

    def test_get_objects_by_type_case_insensitive(self):
        lower = get_objects_by_type("galaxy")
        upper = get_objects_by_type("Galaxy")
        assert len(lower) == len(upper)

    def test_get_objects_for_month_summer(self):
        summer = get_objects_for_month(7)  # July
        assert len(summer) > 0
        for obj in summer:
            assert 7 in obj["best_months"]

    def test_get_objects_for_month_returns_subset(self):
        for month in range(1, 13):
            results = get_objects_for_month(month)
            assert len(results) <= len(DSO_CATALOG)

    def test_get_objects_by_filter_narrowband(self):
        nb = get_objects_by_filter("narrowband")
        assert len(nb) > 0
        assert all(o["filter_type"] == "narrowband" for o in nb)

    def test_get_objects_by_filter_broadband(self):
        bb = get_objects_by_filter("broadband")
        assert len(bb) > 0


class TestTypeIcon:
    def test_galaxy_icon(self):
        assert type_icon("Galaxy") == "🌀"

    def test_emission_nebula_icon(self):
        assert type_icon("Emission Nebula") == "🌌"

    def test_globular_cluster_icon(self):
        assert type_icon("Globular Cluster") == "⭐"

    def test_open_cluster_icon(self):
        assert type_icon("Open Cluster") == "⭐"

    def test_unknown_type_returns_fallback(self):
        icon = type_icon("Quasar")
        assert isinstance(icon, str)
        assert len(icon) > 0


class TestRatingStars:
    def test_five_stars(self):
        assert rating_stars(5) == "★★★★★"

    def test_three_stars(self):
        assert rating_stars(3) == "★★★☆☆"

    def test_one_star(self):
        assert rating_stars(1) == "★☆☆☆☆"

    def test_zero_stars(self):
        assert rating_stars(0) == "☆☆☆☆☆"

    def test_total_length_always_five(self):
        for n in range(6):
            s = rating_stars(n)
            assert len(s) == 5
