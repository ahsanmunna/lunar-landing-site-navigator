"""Tests for lunar_engine.geometry: forward, inverse, scale factor, and frames."""

import numpy as np
import pytest

from lunar_engine.geometry import (
    forward,
    inverse,
    latlon_to_xy,
    xy_to_latlon,
    map_scale_factor,
    map_local_frame,
    map_azimuth_directions,
    site_local_frame,
    site_position_km,
)


@pytest.mark.parametrize(
    "lat,lon",
    [
        (-86.0, 2.0),
        (-87.3, 77.0),
        (-80.0, 0.0),
        (-82.5, 180.0),
        (-85.0, -120.0),
        (-89.5, 45.0),
        (-89.99, -179.9),
    ],
)
def test_geometry_round_trip(lat, lon):
    """Geometry forward and inverse projection round trips within 1e-6 degrees."""
    x, y = forward(lat, lon)
    lat_rec, lon_rec = inverse(x, y)

    assert lat_rec == pytest.approx(lat, abs=1e-6)
    # Longitude difference modulo 360
    lon_diff = (lon_rec - lon + 180.0) % 360.0 - 180.0
    assert lon_diff == pytest.approx(0.0, abs=1e-6)


def test_south_pole_lat_neg_90_does_not_crash():
    """Exact lat == -90 (rho0 = 0) does not crash and defines north as lon=0 direction."""
    # Forward and inverse
    x, y = forward(-90.0, 0.0)
    assert x == 0.0
    assert y == 0.0
    lat_rec, lon_rec = inverse(0.0, 0.0)
    assert lat_rec == -90.0
    assert lon_rec == 0.0

    # Scale factor
    k0 = map_scale_factor(-90.0)
    assert k0 == pytest.approx(1.0)

    # 2D Map frame
    north_2d, east_2d = map_local_frame(-90.0, 0.0)
    # North defined as lon=0 direction, which is +y on this polar stereographic projection
    np.testing.assert_allclose(north_2d, [0.0, 1.0], atol=1e-12)
    np.testing.assert_allclose(east_2d, [1.0, 0.0], atol=1e-12)

    # Azimuth directions (360, 2)
    dirs = map_azimuth_directions(-90.0, 0.0, 360)
    assert dirs.shape == (360, 2)
    assert not np.any(np.isnan(dirs))

    # 3D Local frame
    up, east, north = site_local_frame(-90.0, 0.0)
    # At South Pole in MOON_ME frame:
    # Up points towards -Z (outward from surface)
    np.testing.assert_allclose(up, [0.0, 0.0, -1.0], atol=1e-12)
    # North is defined along lon=0 (+X)
    np.testing.assert_allclose(north, [1.0, 0.0, 0.0], atol=1e-12)
    # East is along lon=90 (+Y)
    np.testing.assert_allclose(east, [0.0, 1.0, 0.0], atol=1e-12)

    # Site position vector
    pos = site_position_km(-90.0, 0.0, 0.0, observer_height_m=2.0)
    assert pos.shape == (3,)
    assert pos[2] < 0.0  # -Z axis


def test_site_local_frame_orthonormality():
    """Verify that (east, north, up) forms an orthonormal right-handed triad."""
    for lat in [-80.0, -85.0, -88.0, -90.0]:
        for lon in [0.0, 45.0, 180.0, -90.0]:
            up, east, north = site_local_frame(lat, lon)
            assert np.linalg.norm(up) == pytest.approx(1.0)
            assert np.linalg.norm(east) == pytest.approx(1.0)
            assert np.linalg.norm(north) == pytest.approx(1.0)
            assert np.dot(up, east) == pytest.approx(0.0, abs=1e-12)
            assert np.dot(up, north) == pytest.approx(0.0, abs=1e-12)
            assert np.dot(east, north) == pytest.approx(0.0, abs=1e-12)
            # Right-handedness: east x north = up
            cross = np.cross(east, north)
            np.testing.assert_allclose(cross, up, atol=1e-12)
