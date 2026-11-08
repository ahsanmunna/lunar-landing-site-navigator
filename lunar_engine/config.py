"""Configuration and constants for lunar_engine.

Provides paths, environment variable lookups, and physical constants for lunar
terrain analysis and ephemeris calculations.
"""

from pathlib import Path
import os
from typing import Optional, Union

# Lunar reference sphere radius (m) matching LOLA DEM
MOON_RADIUS_M: float = 1737400.0
MOON_RADIUS_KM: float = MOON_RADIUS_M / 1000.0

# Physical radii of solar system bodies (km)
SUN_RADIUS_KM: float = 695700.0
EARTH_RADIUS_KM: float = 6371.0

# SPICE ephemeris defaults
SPICE_FRAME: str = "MOON_ME"
SPICE_ABCORR: str = "NONE"
SPICE_OBSERVER: str = "MOON"

# Standard kernel filenames
STANDARD_KERNELS = (
    "naif0012.tls",
    "de440.bsp",
    "moon_pa_de440_200625.bpc",
    "moon_de440_220930.tf",
)

# Simulation defaults
DEFAULT_STEP_S: float = 900.0
DEFAULT_OBSERVER_HEIGHT_M: float = 2.0
DEFAULT_START: str = "2027-01-01"
DEFAULT_DAYS: int = 30
DEFAULT_CACHE_FILENAME: str = "dem_160m_cache.npy"


def get_dem_path(custom_path: Optional[Union[str, Path]] = None) -> Optional[Path]:
    """Return path to LOLA DEM TIFF from custom arg or LUNAR_DEM_PATH environment variable."""
    if custom_path is not None:
        p = Path(custom_path)
        return p if p.exists() else None
    env_val = os.environ.get("LUNAR_DEM_PATH")
    if env_val:
        p = Path(env_val)
        return p if p.exists() else None
    return None


def get_kernel_dir(custom_dir: Optional[Union[str, Path]] = None) -> Path:
    """Resolve directory containing SPICE kernels."""
    if custom_dir is not None:
        return Path(custom_dir)
    # Check current working directory ./kernels
    cwd_kernels = Path.cwd() / "kernels"
    if cwd_kernels.is_dir():
        return cwd_kernels
    # Check parent of package
    pkg_kernels = Path(__file__).resolve().parent.parent / "kernels"
    if pkg_kernels.is_dir():
        return pkg_kernels
    return cwd_kernels


def get_cache_path(custom_path: Optional[Union[str, Path]] = None) -> Path:
    """Resolve path to the 160 m downsampled DEM cache file."""
    if custom_path is not None:
        return Path(custom_path)
    cwd_cache = Path.cwd() / DEFAULT_CACHE_FILENAME
    if cwd_cache.exists():
        return cwd_cache
    pkg_cache = Path(__file__).resolve().parent.parent / DEFAULT_CACHE_FILENAME
    if pkg_cache.exists():
        return pkg_cache
    return cwd_cache
