"""SPICE ephemeris calculations for Sun and Earth positions and angular radii.

Computes Moon-centered and site-relative (topocentric) positions, azimuth/elevation,
and distance-based angular radii in the MOON_ME frame.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Union
import numpy as np
import spiceypy as spice

from lunar_engine.config import (
    SUN_RADIUS_KM,
    EARTH_RADIUS_KM,
    SPICE_FRAME,
    SPICE_ABCORR,
    SPICE_OBSERVER,
    DEFAULT_STEP_S,
    DEFAULT_OBSERVER_HEIGHT_M,
    DEFAULT_START,
    DEFAULT_DAYS,
    get_kernel_dir,
)
from lunar_engine.geometry import site_local_frame, site_position_km

_KERNELS_LOADED = False


def load_kernels(kernel_dir: Optional[Union[str, Path]] = None) -> None:
    """Furnish required SPICE kernels (TLS, BSP, BPC, TF) if not already loaded."""
    global _KERNELS_LOADED
    kdir = get_kernel_dir(kernel_dir)
    spk = "de440.bsp"
    if not (kdir / spk).exists() and (kdir / "de440s.bsp").exists():
        spk = "de440s.bsp"
    required = ["naif0012.tls", spk, "moon_pa_de440_200625.bpc", "moon_de440_220930.tf"]
    for k in required:
        kp = kdir / k
        if not kp.exists():
            raise FileNotFoundError(f"Missing required SPICE kernel: {kp}")

    if spice.ktotal("ALL") == 0 or not _KERNELS_LOADED:
        for k in required:
            spice.furnsh(str((kdir / k).resolve()))
        _KERNELS_LOADED = True


def create_time_grid(
    start: str,
    days: float,
    step_s: float = DEFAULT_STEP_S,
    kernel_dir: Optional[Union[str, Path]] = None,
) -> np.ndarray:
    """Create an array of ephemeris times (ET in seconds past J2000) for a run."""
    load_kernels(kernel_dir)
    time_str = start if (" " in start or "T" in start) else f"{start} 00:00:00"
    et0 = spice.str2et(time_str)
    total_seconds = float(days) * 86400.0
    return et0 + np.arange(0.0, total_seconds, float(step_s), dtype=np.float64)


def get_moon_centered_positions(
    body: str,
    ets: np.ndarray,
    kernel_dir: Optional[Union[str, Path]] = None,
) -> np.ndarray:
    """Return Moon-centred position vectors (km, MOON_ME, abcorr NONE) of body on time grid."""
    load_kernels(kernel_dir)
    positions = np.empty((len(ets), 3), dtype=np.float64)
    for i, et in enumerate(ets):
        pos, _ = spice.spkpos(body, float(et), SPICE_FRAME, SPICE_ABCORR, SPICE_OBSERVER)
        positions[i] = pos
    return positions


def moon_centered_positions(
    start: str,
    days: float,
    step_s: float = DEFAULT_STEP_S,
    kernel_dir: Optional[Union[str, Path]] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (ets, sun_pos, earth_pos) in km, MOON_ME frame, abcorr NONE on the time grid."""
    ets = create_time_grid(start, days, step_s, kernel_dir=kernel_dir)
    sun_pos = get_moon_centered_positions("SUN", ets, kernel_dir=kernel_dir)
    earth_pos = get_moon_centered_positions("EARTH", ets, kernel_dir=kernel_dir)
    return ets, sun_pos, earth_pos


def sub_body_latlon(
    body: str,
    et: Union[float, str],
    kernel_dir: Optional[Union[str, Path]] = None,
) -> Tuple[float, float]:
    """Return (lat, lon) in degrees of sub-body point on the Moon in MOON_ME frame."""
    load_kernels(kernel_dir)
    et_val = spice.str2et(et) if isinstance(et, str) else float(et)
    pos, _ = spice.spkpos(body, et_val, SPICE_FRAME, SPICE_ABCORR, SPICE_OBSERVER)
    _, lon, lat = spice.reclat(pos)
    return float(lat * spice.dpr()), float(lon * spice.dpr())


def angular_radius_deg(radius_km: float, distance_km: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
    """Compute apparent angular radius in degrees: arcsin(R / distance)."""
    return np.degrees(np.arcsin(radius_km / distance_km))


@dataclass
class EphemerisData:
    """Azimuth, elevation, and angular radii for Sun and Earth over time."""
    sun: np.ndarray            # (N, 2) [azimuth, elevation] in degrees
    earth: np.ndarray          # (N, 2) [azimuth, elevation] in degrees
    sun_r: np.ndarray          # (N,) angular radius in degrees
    earth_r: np.ndarray        # (N,) angular radius in degrees
    ets: np.ndarray            # (N,) ephemeris times
    sun_dist_km: np.ndarray    # (N,) distance in km
    earth_dist_km: np.ndarray  # (N,) distance in km

    def __iter__(self):
        """Allow unpacking: sun, earth, sun_r, earth_r = result."""
        return iter((self.sun, self.earth, self.sun_r, self.earth_r))

    def __getitem__(self, item: str):
        """Allow dict-style key access."""
        return getattr(self, item)


def sun_earth_azel(
    lat: float,
    lon: float,
    ground_height_m: float,
    observer_height_m: float = DEFAULT_OBSERVER_HEIGHT_M,
    start: str = DEFAULT_START,
    days: float = DEFAULT_DAYS,
    step_s: float = DEFAULT_STEP_S,
    kernel_dir: Optional[Union[str, Path]] = None,
) -> EphemerisData:
    """Compute Sun and Earth (azimuth, elevation) and angular radii in the site's local frame.
    
    Parameters
    ----------
    lat : float
        Site latitude in degrees.
    lon : float
        Site longitude in degrees.
    ground_height_m : float
        Ground elevation above reference sphere in metres.
    observer_height_m : float
        Observer height above local ground in metres (default 2.0).
    start : str
        Start date/time UTC (default "2027-01-01").
    days : float
        Duration in days (default 30).
    step_s : float
        Time step in seconds (default 900.0).
    kernel_dir : str or Path, optional
        Path to SPICE kernels directory.
        
    Returns
    -------
    EphemerisData
        Dataclass containing sun and earth (N, 2) azimuth/elevation arrays,
        (N,) distance-derived angular radii arrays, and ephemeris times.
    """
    load_kernels(kernel_dir)
    ets = create_time_grid(start, days, step_s, kernel_dir=kernel_dir)
    up, e3, n3 = site_local_frame(lat, lon)
    r_site = site_position_km(lat, lon, ground_height_m, observer_height_m)

    sun_pos = get_moon_centered_positions("SUN", ets, kernel_dir=kernel_dir)
    earth_pos = get_moon_centered_positions("EARTH", ets, kernel_dir=kernel_dir)

    def _topocentric(pos_moon: np.ndarray, radius_km: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        v = pos_moon - r_site[None, :]
        dist = np.linalg.norm(v, axis=1)
        v_unit = v / dist[:, None]
        az = np.degrees(np.arctan2(v_unit @ e3, v_unit @ n3)) % 360.0
        el = np.degrees(np.arcsin(np.clip(v_unit @ up, -1.0, 1.0)))
        r_ang = angular_radius_deg(radius_km, dist)
        azel = np.column_stack((az, el))
        return azel, r_ang, dist

    sun_azel, sun_r, sun_dist = _topocentric(sun_pos, SUN_RADIUS_KM)
    earth_azel, earth_r, earth_dist = _topocentric(earth_pos, EARTH_RADIUS_KM)

    return EphemerisData(
        sun=sun_azel,
        earth=earth_azel,
        sun_r=sun_r,
        earth_r=earth_r,
        ets=ets,
        sun_dist_km=sun_dist,
        earth_dist_km=earth_dist,
    )
