"""South polar stereographic forward and inverse coordinate transformations.

Provides forward (lat, lon) -> (x, y) and inverse (x, y) -> (lat, lon)
transformations on a spherical Moon (radius 1737400 m) independent of
the lunar_engine package.
"""

from typing import Tuple
import numpy as np

# Standard lunar reference sphere radius matching LOLA DEM (m)
MOON_RADIUS_M: float = 1737400.0


def forward(lat: float, lon: float, r_moon: float = MOON_RADIUS_M) -> Tuple[float, float]:
    """Convert (lat, lon) in degrees to south polar stereographic (x, y) in metres.

    Near side is up (+y direction, lon=0), east is right (+x direction, lon=90).
    At the South Pole (lat = -90), returns (0.0, 0.0).
    """
    colat = np.radians(90.0 + lat)
    rho = 2.0 * r_moon * np.tan(colat / 2.0)
    lon_rad = np.radians(lon)
    x = rho * np.sin(lon_rad)
    y = rho * np.cos(lon_rad)
    return float(x), float(y)


def inverse(x: float, y: float, r_moon: float = MOON_RADIUS_M) -> Tuple[float, float]:
    """Convert south polar stereographic (x, y) in metres to (lat, lon) in degrees.

    At (0, 0), returns (-90.0, 0.0).
    """
    rho = float(np.hypot(x, y))
    if rho == 0.0:
        return -90.0, 0.0
    colat = 2.0 * np.arctan(rho / (2.0 * r_moon))
    lat = float(np.degrees(colat) - 90.0)
    lon = float(np.degrees(np.arctan2(x, y)))
    return lat, lon


# Descriptive aliases
latlon_to_xy = forward
xy_to_latlon = inverse
