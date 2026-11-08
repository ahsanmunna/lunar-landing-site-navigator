"""Tests for lunar_engine.ephemeris: SPICE positions, angular radii, and topocentric tracks."""

import numpy as np
import pytest

from lunar_engine.config import EARTH_RADIUS_KM, SUN_RADIUS_KM
from lunar_engine.ephemeris import (
    load_kernels,
    sub_body_latlon,
    angular_radius_deg,
    moon_centered_positions,
    sun_earth_azel,
)


@pytest.fixture(scope="module", autouse=True)
def setup_spice():
    """Ensure SPICE kernels are loaded before running ephemeris tests."""
    load_kernels()


def test_spice_sub_points_check():
    """SPICE check for 2026-06-18 18:00 UT:
    sub-Earth point within 0.05 deg of (lat -1.600, lon 6.545 E)
    and sub-solar longitude within 0.05 deg of 135.917 E.
    """
    earth_lat, earth_lon = sub_body_latlon("EARTH", "2026-06-18 18:00:00 UTC")
    sun_lat, sun_lon = sub_body_latlon("SUN", "2026-06-18 18:00:00 UTC")

    assert earth_lat == pytest.approx(-1.600, abs=0.05)
    assert earth_lon == pytest.approx(6.545, abs=0.05)
    assert sun_lon == pytest.approx(135.917, abs=0.05)


def test_angular_radius_calculation():
    """c) Angular radius test: Earth radius from the vector at a known distance equals asin(6371/d)."""
    # Test with known distance d = 384400 km
    d = 384400.0
    expected_deg = np.degrees(np.arcsin(EARTH_RADIUS_KM / d))
    actual_deg = angular_radius_deg(EARTH_RADIUS_KM, d)
    assert actual_deg == pytest.approx(expected_deg, abs=1e-12)

    # Test array of distances
    d_arr = np.array([360000.0, 384400.0, 405000.0])
    expected_arr = np.degrees(np.arcsin(6371.0 / d_arr))
    actual_arr = angular_radius_deg(6371.0, d_arr)
    np.testing.assert_allclose(actual_arr, expected_arr, atol=1e-12)

    # Sun angular radius test
    d_sun = 1.496e8  # ~1 AU
    expected_sun_deg = np.degrees(np.arcsin(SUN_RADIUS_KM / d_sun))
    assert angular_radius_deg(SUN_RADIUS_KM, d_sun) == pytest.approx(expected_sun_deg, abs=1e-12)


def test_moon_centered_raw_vectors():
    """ephemeris.py can return the raw Moon-centred SUN and EARTH vectors on a time grid."""
    ets, sun_pos, earth_pos = moon_centered_positions("2027-01-01", days=1, step_s=3600.0)
    assert len(ets) == 24
    assert sun_pos.shape == (24, 3)
    assert earth_pos.shape == (24, 3)

    # Moon-Earth distance is roughly 350,000 to 410,000 km
    earth_dist = np.linalg.norm(earth_pos, axis=1)
    assert np.all((earth_dist > 350000.0) & (earth_dist < 410000.0))

    # Moon-Sun distance is roughly 1.47e8 to 1.52e8 km
    sun_dist = np.linalg.norm(sun_pos, axis=1)
    assert np.all((sun_dist > 1.4e8) & (sun_dist < 1.6e8))


@pytest.mark.parametrize("observer_height", [1.0, 2.0, 5.0])
def test_observer_heights_supported(observer_height):
    """Observer height is a parameter; support 1 m and 5 m (default 2 m)."""
    res = sun_earth_azel(
        lat=-86.0,
        lon=2.0,
        ground_height_m=5154.0,
        observer_height_m=observer_height,
        start="2027-01-01",
        days=0.5,
        step_s=3600.0,
    )
    assert res.sun.shape[0] == 12
    assert res.earth.shape[0] == 12
    assert len(res.sun_r) == 12
    assert len(res.earth_r) == 12
