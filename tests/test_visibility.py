"""Tests for lunar_engine.visibility: disc visible fraction, run lengths, and summary."""

import numpy as np
import pytest

from lunar_engine.visibility import (
    disc_visible_fraction,
    visible_fraction,
    longest_run,
    summarize,
)


def test_visible_fraction_at_t_minus1_0_1():
    """visible_fraction at t=-1, 0, 1 gives 0, 0.5, 1."""
    # Scalar checks
    assert visible_fraction(t=-1.0) == pytest.approx(0.0, abs=1e-12)
    assert visible_fraction(t=0.0) == pytest.approx(0.5, abs=1e-12)
    assert visible_fraction(t=1.0) == pytest.approx(1.0, abs=1e-12)

    # Calling with single positional argument t
    assert visible_fraction(-1.0) == pytest.approx(0.0, abs=1e-12)
    assert visible_fraction(0.0) == pytest.approx(0.5, abs=1e-12)
    assert visible_fraction(1.0) == pytest.approx(1.0, abs=1e-12)

    # Vector checks
    t_vals = np.array([-1.0, 0.0, 1.0])
    res = visible_fraction(t_vals)
    np.testing.assert_allclose(res, [0.0, 0.5, 1.0], atol=1e-12)

    # Clipping outside [-1, 1]
    assert visible_fraction(-2.5) == 0.0
    assert visible_fraction(3.0) == 1.0


def test_longest_run():
    """Verify run-length calculation on boolean sequences."""
    assert longest_run([]) == 0
    assert longest_run([False, False]) == 0
    assert longest_run([True, True, True]) == 3
    assert longest_run([True, False, True, True, False, True]) == 2
    assert longest_run([False, True, True, True, True, False]) == 4


def test_summarize_metrics():
    """Verify summarize() calculates metrics and scales run durations using step_s."""
    hor = np.zeros(360, dtype=np.float64)  # flat horizon at 0 deg elevation
    ground_height_m = 1234.0
    lat = -86.0
    lon = 2.0

    # 4 time steps, step_s = 900 s (0.25 h each)
    # Sun elevation: -1, 0, 1, 2 deg with r=1 deg -> t = -1, 0, 1, 1 -> sv = 0.0, 0.5, 1.0, 1.0
    sun_azel = np.array([[0, -1.0], [90, 0.0], [180, 1.0], [270, 2.0]])
    sun_r = 1.0

    # Earth elevation: all below horizon -> ev = 0.0 for 4 steps
    earth_azel = np.array([[0, -2.0], [90, -3.0], [180, -2.5], [270, -4.0]])
    earth_r = 1.0

    step_s = 900.0  # 15 minutes = 0.25 hours
    res = summarize(
        hor=hor,
        ground_height_m=ground_height_m,
        sun=sun_azel,
        sun_r=sun_r,
        earth=earth_azel,
        earth_r=earth_r,
        lat=lat,
        lon=lon,
        start="2027-01-01",
        days=0.0416667,
        observer_height_m=2.0,
        step_s=step_s,
    )

    # Sun: fractions [0.0, 0.5, 1.0, 1.0] -> avg = 0.625
    assert res["illumination_avg_fraction"] == pytest.approx(0.625)
    # 3 out of 4 have sun > 0 -> 75%
    assert res["sun_any_pct"] == pytest.approx(75.0)
    # 1 step with sun == 0 -> 1 * 900 / 3600 = 0.25 h
    assert res["sun_longest_dark_h"] == pytest.approx(0.25)

    # Earth: all 0.0 -> earth_any = 0%, earth_mostly = 0%
    assert res["earth_any_pct"] == 0.0
    assert res["earth_mostly_pct"] == 0.0
    # 4 consecutive blackout steps -> 4 * 900 / 3600 = 1.0 h
    assert res["earth_longest_blackout_h"] == pytest.approx(1.0)

    # Horizon and ground
    assert res["horizon_min"] == 0.0
    assert res["horizon_max"] == 0.0
    assert res["ground_height_m"] == 1234.0

    # Inputs dictionary
    assert "inputs" in res
    assert res["inputs"]["lat"] == -86.0
    assert res["inputs"]["step_s"] == 900.0
    assert res["step_s"] == 900.0
