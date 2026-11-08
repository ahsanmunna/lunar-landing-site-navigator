"""Visibility fraction, metrics summary, and panorama visualization.

Calculates partial disc obscuration by terrain, sunlight and Earth visibility statistics,
and renders horizon panorama plots.
"""

from pathlib import Path
from typing import Any, Dict, Optional, Union
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from lunar_engine.config import (
    DEFAULT_STEP_S,
    DEFAULT_OBSERVER_HEIGHT_M,
    DEFAULT_START,
    DEFAULT_DAYS,
)


def disc_visible_fraction(t: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
    """Compute the visible area fraction of a spherical disc given normalized offset t in [-1, 1].
    
    t = -1: completely below horizon -> 0.0
    t =  0: center of disc on horizon -> 0.5
    t = +1: completely above horizon -> 1.0
    """
    t_arr = np.clip(np.asarray(t, dtype=np.float64), -1.0, 1.0)
    frac = (np.arccos(-t_arr) + t_arr * np.sqrt(1.0 - t_arr ** 2)) / np.pi
    if np.ndim(t) == 0:
        return float(frac)
    return frac


def visible_fraction(
    body: Optional[Union[np.ndarray, float]] = None,
    r: Optional[Union[np.ndarray, float]] = None,
    hor: Optional[np.ndarray] = None,
    *,
    t: Optional[Union[np.ndarray, float]] = None,
) -> Union[np.ndarray, float]:
    """Calculate the visible area fraction of a disc over the terrain horizon.
    
    Can be called either as:
      visible_fraction(body, r, hor)  where body is (N, 2) [az, el], r is angular radius, hor is (360,)
    or directly with normalized altitude offset t:
      visible_fraction(t)
      visible_fraction(t=t)
    """
    if t is not None:
        return disc_visible_fraction(t)
    if body is not None and r is None and hor is None:
        return disc_visible_fraction(body)
    if body is None or r is None or hor is None:
        raise ValueError("Must provide either 't' or ('body', 'r', 'hor')")

    body_arr = np.asarray(body)
    az = body_arr[:, 0]
    el = body_arr[:, 1]
    hz = np.interp(az, np.arange(360), hor, period=360)
    t_val = (el - hz) / r
    return disc_visible_fraction(t_val)


def longest_run(mask: Union[np.ndarray, list]) -> int:
    """Return the length of the longest consecutive sequence of True values."""
    best = cur = 0
    for m in mask:
        cur = cur + 1 if m else 0
        best = max(best, cur)
    return best


def summarize(
    hor: np.ndarray,
    ground_height_m: float,
    sun: np.ndarray,
    sun_r: Union[np.ndarray, float],
    earth: np.ndarray,
    earth_r: Union[np.ndarray, float],
    lat: float,
    lon: float,
    start: str = DEFAULT_START,
    days: float = DEFAULT_DAYS,
    observer_height_m: float = DEFAULT_OBSERVER_HEIGHT_M,
    step_s: float = DEFAULT_STEP_S,
    **extra_inputs: Any,
) -> Dict[str, Any]:
    """Summarize illumination and communication visibility metrics for a site over time.
    
    Parameters
    ----------
    hor : np.ndarray
        Terrain horizon elevation angles (360,).
    ground_height_m : float
        Ground height of the site in metres.
    sun : np.ndarray
        Sun (N, 2) [azimuth, elevation] in degrees.
    sun_r : np.ndarray or float
        Sun angular radius in degrees.
    earth : np.ndarray
        Earth (N, 2) [azimuth, elevation] in degrees.
    earth_r : np.ndarray or float
        Earth angular radius in degrees.
    lat : float
        Latitude in degrees.
    lon : float
        Longitude in degrees.
    start : str
        Simulation start date/time.
    days : float
        Simulation length in days.
    observer_height_m : float
        Observer height in metres.
    step_s : float
        Time step in seconds.
        
    Returns
    -------
    dict
        Summary dictionary containing:
        - illumination_avg_fraction
        - sun_any_pct
        - sun_longest_dark_h
        - earth_any_pct
        - earth_mostly_pct
        - earth_longest_blackout_h
        - horizon_min
        - horizon_max
        - ground_height_m
        - inputs dictionary and input parameters
    """
    sv = visible_fraction(sun, sun_r, hor)
    ev = visible_fraction(earth, earth_r, hor)

    sun_longest_dark_steps = longest_run(sv == 0.0)
    earth_longest_blackout_steps = longest_run(ev == 0.0)

    # Convert consecutive steps to hours using step_s
    sun_longest_dark_h = float(sun_longest_dark_steps * step_s / 3600.0)
    earth_longest_blackout_h = float(earth_longest_blackout_steps * step_s / 3600.0)

    inputs_dict = {
        "lat": float(lat),
        "lon": float(lon),
        "ground_height_m": float(ground_height_m),
        "observer_height_m": float(observer_height_m),
        "start": str(start),
        "days": float(days),
        "step_s": float(step_s),
        **extra_inputs,
    }

    return {
        "illumination_avg_fraction": float(np.mean(sv)),
        "sun_any_pct": float(np.mean(sv > 0.0) * 100.0),
        "sun_longest_dark_h": sun_longest_dark_h,
        "earth_any_pct": float(np.mean(ev > 0.0) * 100.0),
        "earth_mostly_pct": float(np.mean(ev > 0.5) * 100.0),
        "earth_longest_blackout_h": earth_longest_blackout_h,
        "horizon_min": float(np.min(hor)),
        "horizon_max": float(np.max(hor)),
        "ground_height_m": float(ground_height_m),
        "inputs": inputs_dict,
        "lat": float(lat),
        "lon": float(lon),
        "start": str(start),
        "days": float(days),
        "observer_height_m": float(observer_height_m),
        "step_s": float(step_s),
    }


def plot_panorama(
    hor: np.ndarray,
    sun: np.ndarray,
    earth: np.ndarray,
    lat: float,
    lon: float,
    start: str,
    days: float,
    output_path: Union[str, Path] = "site_panorama.png",
) -> Path:
    """Render and save horizon panorama plot with Sun and Earth tracks."""
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.fill_between(np.arange(360), -10, hor, color="0.35", label="terrain horizon")
    ax.scatter(sun[:, 0], sun[:, 1], s=6, c="orange", label="Sun")
    ax.scatter(earth[:, 0], earth[:, 1], s=6, c="tab:blue", label="Earth")
    ax.set_xlim(0, 360)
    ax.set_ylim(
        min(float(np.min(hor)), -1.0) - 0.5,
        max(float(np.max(hor)), float(np.max(sun[:, 1])), float(np.max(earth[:, 1]))) + 1.0,
    )
    ax.set_xlabel("azimuth (deg from north, clockwise)")
    ax.set_ylabel("elevation (deg)")
    ax.set_title(f"Lat {lat}, lon {lon}: {start}, {days} days")
    ax.legend(loc="upper right")
    fig.savefig(out_p, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return out_p
