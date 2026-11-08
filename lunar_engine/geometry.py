"""Coordinate transformations and local frames for lunar surface analysis.

Handles south polar stereographic projection (forward and inverse), scale factors,
and local reference frames (both 2D map directions and 3D MOON_ME topocentric frames),
with exact handling of the South Pole (lat = -90).
"""

from typing import Tuple
import numpy as np
from lunar_engine.config import MOON_RADIUS_M, DEFAULT_OBSERVER_HEIGHT_M


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


def map_scale_factor(lat: float) -> float:
    """Return map scale factor k0 at given latitude for south polar stereographic projection."""
    colat = np.radians(90.0 + lat)
    k0 = 1.0 / (np.cos(colat / 2.0) ** 2)
    return float(k0)


def map_local_frame(lat: float, lon: float) -> Tuple[np.ndarray, np.ndarray]:
    """Return (north, east) unit direction vectors in the 2D map plane.
    
    "North" points away from the South Pole (toward lon=0 at lat=-90).
    "East" points 90 degrees clockwise from north.
    """
    x0, y0 = forward(lat, lon)
    rho0 = np.hypot(x0, y0)
    if rho0 == 0.0 or np.isclose(lat, -90.0):
        # At South Pole, define north as lon=0 direction (+y), east as +x
        north = np.array([0.0, 1.0], dtype=np.float64)
        east = np.array([1.0, 0.0], dtype=np.float64)
    else:
        north = np.array([x0, y0], dtype=np.float64) / rho0
        east = np.array([y0, -x0], dtype=np.float64) / rho0
    return north, east


def map_azimuth_directions(lat: float, lon: float, n_azimuths: int = 360) -> np.ndarray:
    """Return unit vectors (n_azimuths, 2) on 2D map for azimuths 0..359 deg clockwise from north."""
    north, east = map_local_frame(lat, lon)
    az = np.radians(np.arange(0, n_azimuths, 360.0 / n_azimuths, dtype=np.float64))
    dirs = np.outer(np.cos(az), north) + np.outer(np.sin(az), east)
    return dirs


def site_local_frame(lat: float, lon: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return 3D unit vectors (up, east, north) in MOON_ME frame at given (lat, lon).
    
    At lat == -90, north is defined as the lon=0 direction.
    """
    if np.isclose(lat, -90.0):
        up = np.array([0.0, 0.0, -1.0], dtype=np.float64)
        east = np.array([0.0, 1.0, 0.0], dtype=np.float64)
        north = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    else:
        la = np.radians(lat)
        lo = np.radians(lon)
        up = np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], dtype=np.float64)
        east = np.array([-np.sin(lo), np.cos(lo), 0.0], dtype=np.float64)
        north = np.array([-np.sin(la) * np.cos(lo), -np.sin(la) * np.sin(lo), np.cos(la)], dtype=np.float64)
    return up, east, north


def site_position_km(
    lat: float,
    lon: float,
    ground_height_m: float,
    observer_height_m: float = DEFAULT_OBSERVER_HEIGHT_M,
    r_moon_m: float = MOON_RADIUS_M,
) -> np.ndarray:
    """Return 3D position vector in km in the MOON_ME frame for an observer at the site."""
    up, _, _ = site_local_frame(lat, lon)
    return (r_moon_m + ground_height_m + observer_height_m) / 1000.0 * up
