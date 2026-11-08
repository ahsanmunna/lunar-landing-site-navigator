"""Regression tests comparing refactored package output with baseline numbers.

Requires LOLA DEM specified via LUNAR_DEM_PATH. Skips cleanly if unset.
"""

import os
from pathlib import Path
import pytest

from lunar_engine.config import get_dem_path
from lunar_engine.horizon import compute_horizon
from lunar_engine.ephemeris import sun_earth_azel
from lunar_engine.visibility import summarize

dem_available = get_dem_path() is not None and get_dem_path().exists()


@pytest.mark.skipif(not dem_available, reason="LUNAR_DEM_PATH is unset or DEM file not found")
def test_regression_site_1():
    """Site 1 (lat -86, lon 2):
    previously illumination 0.84, earth_mostly 45%, earth_any 49%,
    longest Earth blackout 212 h, ground height 5154 m, horizon_min -5.10, max 3.64.
    Tolerances: illumination +-0.02, earth pcts +-2, blackout +-6 h.
    """
    lat, lon = -86.0, 2.0
    start = "2027-01-01"
    days = 30
    step_s = 3600.0
    observer_height_m = 2.0

    hor, ground_height_m = compute_horizon(lat, lon, observer_height_m=observer_height_m)
    assert ground_height_m == pytest.approx(5154.0, abs=10.0)
    assert float(hor.min()) == pytest.approx(-5.10, abs=0.05)
    assert float(hor.max()) == pytest.approx(3.64, abs=0.05)

    ephem = sun_earth_azel(
        lat=lat,
        lon=lon,
        ground_height_m=ground_height_m,
        observer_height_m=observer_height_m,
        start=start,
        days=days,
        step_s=step_s,
    )

    metrics = summarize(
        hor=hor,
        ground_height_m=ground_height_m,
        sun=ephem.sun,
        sun_r=ephem.sun_r,
        earth=ephem.earth,
        earth_r=ephem.earth_r,
        lat=lat,
        lon=lon,
        start=start,
        days=days,
        observer_height_m=observer_height_m,
        step_s=step_s,
    )

    # Illumination tolerance +-0.02
    assert metrics["illumination_avg_fraction"] == pytest.approx(0.84, abs=0.02)

    # Earth pcts tolerance +-2
    assert metrics["earth_mostly_pct"] == pytest.approx(45.0, abs=2.0)
    assert metrics["earth_any_pct"] == pytest.approx(49.0, abs=2.0)

    # Earth blackout tolerance +-6 h
    assert metrics["earth_longest_blackout_h"] == pytest.approx(212.0, abs=6.0)


@pytest.mark.skipif(not dem_available, reason="LUNAR_DEM_PATH is unset or DEM file not found")
def test_regression_site_2():
    """Site 2 (lat -87.3, lon 77):
    illumination 0, earth_any 0, horizon_min greater than 6.0.
    """
    lat, lon = -87.3, 77.0
    start = "2027-01-01"
    days = 30
    step_s = 3600.0
    observer_height_m = 2.0

    hor, ground_height_m = compute_horizon(lat, lon, observer_height_m=observer_height_m)
    assert float(hor.min()) > 6.0

    ephem = sun_earth_azel(
        lat=lat,
        lon=lon,
        ground_height_m=ground_height_m,
        observer_height_m=observer_height_m,
        start=start,
        days=days,
        step_s=step_s,
    )

    metrics = summarize(
        hor=hor,
        ground_height_m=ground_height_m,
        sun=ephem.sun,
        sun_r=ephem.sun_r,
        earth=ephem.earth,
        earth_r=ephem.earth_r,
        lat=lat,
        lon=lon,
        start=start,
        days=days,
        observer_height_m=observer_height_m,
        step_s=step_s,
    )

    assert metrics["illumination_avg_fraction"] == pytest.approx(0.0, abs=1e-6)
    assert metrics["earth_any_pct"] == pytest.approx(0.0, abs=1e-6)
