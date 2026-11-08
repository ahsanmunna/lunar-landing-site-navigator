"""Terrain horizon calculation from LOLA South Polar DEM.

Computes 360-degree terrain elevation profile and ground height for any lunar
south-pole landing site using high-resolution (20 m) near-field and downsampled
(160 m) regional DEM data.
"""

from pathlib import Path
from typing import Optional, Tuple, Union
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window
from scipy.ndimage import map_coordinates

from lunar_engine.config import (
    MOON_RADIUS_M,
    DEFAULT_OBSERVER_HEIGHT_M,
    get_dem_path,
    get_cache_path,
)
from lunar_engine.geometry import forward, map_scale_factor, map_azimuth_directions


def compute_horizon(
    lat: float,
    lon: float,
    observer_height_m: float = DEFAULT_OBSERVER_HEIGHT_M,
    dem_path: Optional[Union[str, Path]] = None,
    cache_path: Optional[Union[str, Path]] = None,
) -> Tuple[np.ndarray, float]:
    """Compute terrain horizon elevation profile and site ground height.
    
    Parameters
    ----------
    lat : float
        Site latitude in degrees (negative for south).
    lon : float
        Site longitude in degrees east.
    observer_height_m : float
        Observer height above local ground in metres (default 2.0).
    dem_path : str or Path, optional
        Path to LOLA DEM TIFF. Defaults to LUNAR_DEM_PATH environment variable.
    cache_path : str or Path, optional
        Path to 160 m cached DEM numpy array. Defaults to dem_160m_cache.npy.
        
    Returns
    -------
    horizon_deg : np.ndarray
        Array of 360 elevation angles in degrees (one per degree of azimuth).
    ground_height_m : float
        Elevation of the ground at the site in metres above lunar reference sphere.
    """
    dem_resolved = get_dem_path(dem_path)
    if dem_resolved is None or not dem_resolved.exists():
        raise FileNotFoundError(
            f"LOLA DEM not found: {dem_path or 'LUNAR_DEM_PATH not set'}. "
            "Please set the LUNAR_DEM_PATH environment variable or pass dem_path."
        )

    cache_resolved = get_cache_path(cache_path)

    x0, y0 = forward(lat, lon)
    k0 = map_scale_factor(lat)
    dirs = map_azimuth_directions(lat, lon, 360)

    with rasterio.open(dem_resolved) as src:
        h, w = src.height // 8, src.width // 8
        if cache_resolved.exists():
            zf = np.load(cache_resolved)
        else:
            print(f"Building the 160 m copy (saving to {cache_resolved})...", flush=True)
            zf = src.read(1, out_shape=(h, w), resampling=Resampling.average).astype("float32")
            np.save(cache_resolved, zf)

        scale_tf = src.transform.scale(src.width / w, src.height / h)
        tf = (src.transform @ scale_tf) if hasattr(src.transform, "__matmul__") else (src.transform * scale_tf)

        half = 8000.0
        win = Window(
            int((x0 - half - src.transform.c) / src.transform.a),
            int((y0 + half - src.transform.f) / src.transform.e),
            int(2 * half / 20),
            int(2 * half / 20),
        )
        zn = src.read(1, window=win, boundless=True, fill_value=np.nan).astype("float32")
        tn = src.window_transform(win)

    col = (x0 - tn.c) / tn.a - 0.5
    row = (y0 - tn.f) / tn.e - 0.5
    h_site = float(map_coordinates(zn, [[row], [col]], order=1, output=np.float64)[0])

    def horizon_from(z: np.ndarray, transform, dist: np.ndarray) -> np.ndarray:
        d = dist[None, :]
        xs = x0 + dirs[:, 0:1] * d
        ys = y0 + dirs[:, 1:2] * d
        cols = (xs - transform.c) / transform.a - 0.5
        rows = (ys - transform.f) / transform.e - 0.5
        ht = map_coordinates(
            z,
            [rows, cols],
            order=1,
            mode="constant",
            cval=np.nan,
            output=np.float64,
        )
        delta = (d / k0) / MOON_RADIUS_M
        rt = MOON_RADIUS_M + ht
        r0 = MOON_RADIUS_M + h_site + observer_height_m
        ang = np.degrees(np.arctan2(rt * np.cos(delta) - r0, rt * np.sin(delta)))
        return np.nanmax(np.where(np.isnan(ang), -90.0, ang), axis=1)

    hor = np.maximum(
        horizon_from(zn, tn, np.arange(20, 8000, 20.0)),
        horizon_from(zf, tf, np.arange(160, 150000, 160.0)),
    )
    return hor, h_site
